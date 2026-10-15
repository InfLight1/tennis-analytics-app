"""
test_r2_puller.py

Checks the "copy pieces in while the upload is still going" helper in
modal_app.py (r2_puller_remote, _stop_r2_puller, _pull_r2_parts) without
Cloudflare or Modal: a fake storage bucket in memory, a stand-in for the
shared volume, and a temp folder for the job.

An "uploader" puts 30 pieces into the fake bucket over ~3 s while the helper
runs; then the upload finishes the way the server does it (stop the helper,
copy whatever is left). Checks:
1. Every piece ends up in the job's parts folder, byte for byte.
2. The helper copied most pieces while the upload was still going.
3. Nothing is left in the bucket.
4. The helper stopped when asked.

Run directly:
    python Code/test_r2_puller.py
"""

import os
import shutil
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import modal_app as m  # noqa: E402


class FakeBucket:
    """The few S3 calls the helper uses, in memory."""
    def __init__(self):
        self.objects, self.lock = {}, threading.Lock()

    def put(self, key, data):
        with self.lock:
            self.objects[key] = data

    def get_paginator(self, _name):
        bucket = self

        class Pager:
            def paginate(self, Bucket, Prefix):
                with bucket.lock:
                    keys = [k for k in bucket.objects if k.startswith(Prefix)]
                return [{"Contents": [{"Key": k} for k in keys]}]
        return Pager()

    def download_file(self, _bucket, key, path):
        with self.lock:
            data = self.objects[key]
        with open(path, "wb") as f:
            f.write(data)

    def delete_objects(self, Bucket, Delete):
        with self.lock:
            for o in Delete["Objects"]:
                self.objects.pop(o["Key"], None)


class FakeVolume:
    def commit(self):
        pass

    def reload(self):
        pass


if __name__ == "__main__":
    work = tempfile.mkdtemp()
    try:
        bucket = FakeBucket()
        m.JOBS_DIR = work
        m.volume = FakeVolume()
        m._r2 = lambda: (bucket, "b")
        m.PULLER_POLL_S = 0.2
        job = "testjob00001"
        parts = f"{work}/{job}/input/parts"
        os.makedirs(parts)
        pieces = {i: os.urandom(1000 + i) for i in range(30)}

        helper = threading.Thread(target=m.r2_puller_remote.local, args=(job,))
        helper.start()
        for i, data in pieces.items():                  # the browser uploading to the bucket
            bucket.put(m._r2_key(job, i), data)
            time.sleep(0.1)
        during = len(m._part_names(parts))              # copied before the upload finished
        m._stop_r2_puller(job)                          # what the server does at the end
        m._pull_r2_parts(job, parts)
        helper.join(timeout=10)

        names = m._part_names(parts)
        same = all(open(f"{parts}/{i:06d}.part", "rb").read() == d for i, d in pieces.items())
        checks = [
            ("every piece arrived, byte for byte", len(names) == 30 and same),
            (f"helper copied {during} of 30 while uploading", during >= 20),
            ("nothing left in the bucket", not bucket.objects),
            ("helper stopped when asked", not helper.is_alive() and os.path.exists(m._puller_marker(job, "done"))),
        ]
        for name, ok in checks:
            print(f"{'PASS' if ok else 'FAIL'}  {name}")
        sys.exit(0 if all(ok for _, ok in checks) else 1)
    finally:
        shutil.rmtree(work, ignore_errors=True)
