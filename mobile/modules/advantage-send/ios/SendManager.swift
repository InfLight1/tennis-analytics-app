import Foundation
import UIKit

// Sends a match video with the screen off. The file is cut into pieces, each piece becomes one
// transfer in a background session, and iOS carries them on while the app sleeps. Saved state
// means a send picks up where it was after the app is closed.
//
// Steps: cut into pieces -> tell the server the size -> send pieces -> tell the server it's done.
// The two messages to the server go through the background session too, so a phone with no
// signal at Stop still gets going by itself once it finds one.

struct SendJob: Codable {
  enum Phase: String, Codable { case preparing, sending, finishing, signIn = "sign-in", sent, failed }

  var jobId: String
  var title: String
  var apiBase: String
  var session: String?
  var passcode: String?
  var partBytes: Int
  var r2: Bool
  var size: Int = 0
  var parts: Int = 0
  var done: Set<Int> = []
  var attempts: [Int: Int] = [:]
  var phase: Phase = .preparing
  var problem: String?
  var startedAt: Date = Date()
}

final class SendManager: NSObject {
  static let shared = SendManager()
  static let sessionId = "com.advantageai.tennis.send"
  private static let maxAttempts = 40
  private static let copyBytes = 4 * 1024 * 1024

  var onChange: (() -> Void)?

  private let queue = DispatchQueue(label: "com.advantageai.tennis.send.state")
  private var jobs: [String: SendJob] = [:]
  private var inFlight: [String: [Int: Int64]] = [:]
  private var lastChange = Date.distantPast
  private var finishEvents: (() -> Void)?

  private lazy var transfers: URLSession = {
    let config = URLSessionConfiguration.background(withIdentifier: SendManager.sessionId)
    config.sessionSendsLaunchEvents = true
    config.isDiscretionary = false
    config.allowsCellularAccess = true
    config.allowsConstrainedNetworkAccess = true
    config.allowsExpensiveNetworkAccess = true
    config.httpMaximumConnectionsPerHost = 3
    config.timeoutIntervalForResource = 7 * 24 * 3600
    let operations = OperationQueue()
    operations.maxConcurrentOperationCount = 1
    operations.underlyingQueue = queue
    return URLSession(configuration: config, delegate: self, delegateQueue: operations)
  }()

  private override init() {
    super.init()
    queue.sync { load() }
  }

  // MARK: Where things live

  private var root: URL {
    let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
    return base.appendingPathComponent("sends", isDirectory: true)
  }
  private func folder(_ jobId: String) -> URL { root.appendingPathComponent(jobId, isDirectory: true) }
  private func videoFile(_ jobId: String) -> URL { folder(jobId).appendingPathComponent("video") }
  private func partFile(_ jobId: String, _ index: Int) -> URL {
    folder(jobId).appendingPathComponent(String(format: "%06d.part", index))
  }
  private var stateFile: URL { root.appendingPathComponent("state.json") }

  private func load() {
    guard let data = try? Data(contentsOf: stateFile),
          let saved = try? JSONDecoder().decode([String: SendJob].self, from: data) else { return }
    jobs = saved
  }

  private func save() {
    do {
      try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
      let data = try JSONEncoder().encode(jobs)
      try data.write(to: stateFile, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
    } catch {
      NSLog("AdvantageSend: couldn't save state: \(error)")
    }
  }

  private func changed(force: Bool = true) {
    let now = Date()
    if !force && now.timeIntervalSince(lastChange) < 0.5 { return }
    lastChange = now
    let tell = onChange
    DispatchQueue.main.async { tell?() }
  }

  // MARK: Called by the app

  func start(_ o: SendOptions) throws {
    var job = SendJob(jobId: o.jobId, title: o.title, apiBase: o.apiBase, session: o.session, passcode: o.passcode,
                      partBytes: o.partBytes, r2: o.r2)
    try FileManager.default.createDirectory(at: folder(o.jobId), withIntermediateDirectories: true)
    let source = URL(fileURLWithPath: o.filePath.replacingOccurrences(of: "file://", with: ""))
    let target = videoFile(o.jobId)
    if !FileManager.default.fileExists(atPath: target.path) {
      try FileManager.default.moveItem(at: source, to: target)
    }
    let attributes = try FileManager.default.attributesOfItem(atPath: target.path)
    job.size = (attributes[.size] as? NSNumber)?.intValue ?? 0
    job.parts = (job.size + job.partBytes - 1) / job.partBytes
    queue.sync {
      jobs[job.jobId] = job
      save()
    }
    changed()
    queue.async { self.prepare(job.jobId) }
  }

  func list() -> [[String: Any]] {
    queue.sync {
      jobs.values.sorted { $0.startedAt > $1.startedAt }.map { job in
        let sent = job.done.reduce(Int64(0)) { $0 + Int64(partSize(job, $1)) }
        let moving = inFlight[job.jobId]?.values.reduce(0, +) ?? 0
        return [
          "jobId": job.jobId, "title": job.title, "phase": job.phase.rawValue,
          "sentBytes": Double(min(sent + moving, Int64(job.size))), "totalBytes": Double(job.size),
          "problem": job.problem as Any,
        ]
      }
    }
  }

  func remove(_ jobId: String) {
    queue.async {
      self.transfers.getAllTasks { tasks in
        tasks.filter { Tag(task: $0)?.jobId == jobId }.forEach { $0.cancel() }
      }
      self.jobs[jobId] = nil
      self.inFlight[jobId] = nil
      try? FileManager.default.removeItem(at: self.folder(jobId))
      self.save()
      self.changed()
    }
  }

  func updateSignIn(session: String?, passcode: String?) {
    queue.async {
      for id in self.jobs.keys {
        self.jobs[id]?.session = session
        self.jobs[id]?.passcode = passcode
        if self.jobs[id]?.phase == .signIn {
          self.jobs[id]?.phase = .sending
          self.jobs[id]?.problem = nil
        }
      }
      self.save()
      self.reconcile()
    }
  }

  // Reconnects to transfers from before, and restarts anything that isn't moving.
  func wake() {
    queue.async {
      _ = self.transfers
      self.reconcile()
    }
  }

  func backgroundEvents(identifier: String, done: @escaping () -> Void) {
    guard identifier == SendManager.sessionId else { done(); return }
    queue.async {
      self.finishEvents = done
      _ = self.transfers
    }
  }

  // MARK: The steps

  private func partSize(_ job: SendJob, _ index: Int) -> Int {
    index == job.parts - 1 ? job.size - index * job.partBytes : job.partBytes
  }

  private func reconcile() {
    transfers.getAllTasks { [weak self] tasks in
      guard let self else { return }
      self.queue.async {
        let moving = Set(tasks.compactMap { Tag(task: $0) })
        for job in self.jobs.values {
          switch job.phase {
          case .preparing:
            if !moving.contains(Tag(jobId: job.jobId, step: .size)) { self.prepare(job.jobId) }
          case .sending:
            self.sendMissing(job.jobId, moving: moving)
          case .finishing:
            if !moving.contains(Tag(jobId: job.jobId, step: .complete)) { self.finish(job.jobId) }
          case .signIn, .sent, .failed:
            break
          }
        }
      }
    }
  }

  private func prepare(_ jobId: String) {
    let app = BackgroundTime()
    defer { app.end() }
    guard let job = jobs[jobId] else { return }
    do {
      try cut(job)
      try post(job, path: "/api/upload/\(jobId)/size",
               form: "size=\(job.size)&chunk_size=\(job.partBytes)", step: .size)
    } catch {
      fail(jobId, "Couldn't get the video ready to send: \(error.localizedDescription)")
    }
  }

  // Cuts from the end and shortens the file as it goes, so a 6 GB video never needs 12 GB of room.
  private func cut(_ job: SendJob) throws {
    let video = videoFile(job.jobId)
    guard FileManager.default.fileExists(atPath: video.path) else { return }
    let handle = try FileHandle(forUpdating: video)
    defer { try? handle.close() }
    var left = Int(try handle.seekToEnd())
    while left > 0 {
      let index = (left - 1) / job.partBytes
      let start = index * job.partBytes
      let temp = partFile(job.jobId, index).appendingPathExtension("tmp")
      FileManager.default.createFile(atPath: temp.path, contents: nil)
      let out = try FileHandle(forWritingTo: temp)
      try handle.seek(toOffset: UInt64(start))
      var copied = start
      while copied < left {
        let more = min(SendManager.copyBytes, left - copied)
        try autoreleasepool {
          guard let bytes = try handle.read(upToCount: more), !bytes.isEmpty else {
            throw NSError(domain: "AdvantageSend", code: 1)
          }
          try out.write(contentsOf: bytes)
          copied += bytes.count
        }
      }
      try out.close()
      let final = partFile(job.jobId, index)
      try? FileManager.default.removeItem(at: final)
      try FileManager.default.moveItem(at: temp, to: final)
      try handle.truncate(atOffset: UInt64(start))
      left = start
    }
    try handle.close()
    try FileManager.default.removeItem(at: video)
  }

  private func request(_ job: SendJob, path: String) -> URLRequest? {
    guard let url = URL(string: job.apiBase + path) else { return nil }
    var request = URLRequest(url: url)
    if let session = job.session { request.setValue(session, forHTTPHeaderField: "X-Session") }
    if let passcode = job.passcode { request.setValue(passcode, forHTTPHeaderField: "X-Passcode") }
    return request
  }

  // A small form sent through the background session; it waits for a signal if there's none.
  private func post(_ job: SendJob, path: String, form: String, step: Tag.Step) throws {
    guard var request = request(job, path: path) else { return }
    request.httpMethod = "POST"
    request.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")
    let body = folder(job.jobId).appendingPathComponent("\(step.rawValue).form")
    try Data(form.utf8).write(to: body, options: .atomic)
    let task = transfers.uploadTask(with: request, fromFile: body)
    task.taskDescription = Tag(jobId: job.jobId, step: step).text
    task.resume()
  }

  // Sends every piece that isn't on the server and isn't already moving.
  private func sendMissing(_ jobId: String, moving: Set<Tag>) {
    guard let job = jobs[jobId] else { return }
    let waiting = (0..<job.parts).filter { !job.done.contains($0) && !moving.contains(Tag(jobId: jobId, step: .part($0))) }
    if waiting.isEmpty {
      if job.done.count == job.parts && !moving.contains(Tag(jobId: jobId, step: .complete)) { finish(jobId) }
      return
    }
    guard job.r2 else {
      waiting.forEach { enqueue(job, index: $0, request: serverRequest(job, index: $0)) }
      return
    }
    fetchStorageLinks(job, waiting: waiting)
  }

  private func serverRequest(_ job: SendJob, index: Int) -> URLRequest? {
    var r = request(job, path: "/api/upload/\(job.jobId)/part/\(index)")
    r?.httpMethod = "PUT"
    return r
  }

  private func enqueue(_ job: SendJob, index: Int, request: URLRequest?) {
    let file = partFile(job.jobId, index)
    guard let request, FileManager.default.fileExists(atPath: file.path) else {
      fail(job.jobId, "Part of the video was lost on this phone, so it can't be sent. Please film it again.")
      return
    }
    let task = transfers.uploadTask(with: request, fromFile: file)
    task.taskDescription = Tag(jobId: job.jobId, step: .part(index)).text
    task.countOfBytesClientExpectsToSend = Int64(partSize(job, index))
    task.resume()
  }

  // Links straight to storage last 6 hours, so they're asked for just before use.
  private func fetchStorageLinks(_ job: SendJob, waiting: [Int]) {
    let app = BackgroundTime()
    let groups = stride(from: 0, to: waiting.count, by: 200).map { Array(waiting[$0..<min($0 + 200, waiting.count)]) }
    let all = DispatchGroup()
    var links: [Int: String] = [:]
    var signedOut = false
    for group in groups {
      guard let first = group.first, let last = group.last,
            let request = request(job, path: "/api/upload/\(job.jobId)/r2-urls?start=\(first)&count=\(last - first + 1)") else { continue }
      all.enter()
      URLSession.shared.dataTask(with: request) { data, response, _ in
        self.queue.async {
          defer { all.leave() }
          let status = (response as? HTTPURLResponse)?.statusCode ?? 0
          if status == 401 || status == 403 { signedOut = true }
          guard status == 200, let data,
                let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                let urls = json["urls"] as? [String: String] else { return }
          urls.forEach { if let i = Int($0.key) { links[i] = $0.value } }
        }
      }.resume()
    }
    all.notify(queue: queue) {
      defer { app.end() }
      if signedOut { self.needSignIn(job.jobId); return }
      guard let job = self.jobs[job.jobId] else { return }
      for index in waiting {
        guard let link = links[index], let url = URL(string: link) else { continue }
        var r = URLRequest(url: url)
        r.httpMethod = "PUT"
        self.enqueue(job, index: index, request: r)
      }
      self.save()
      self.changed()
    }
  }

  private func finish(_ jobId: String) {
    guard let job = jobs[jobId] else { return }
    jobs[jobId]?.phase = .finishing
    save()
    changed()
    let seconds = Int(Date().timeIntervalSince(job.startedAt))
    do {
      try post(job, path: "/api/upload/\(jobId)/complete", form: "upload_seconds=\(seconds)", step: .complete)
    } catch {
      fail(jobId, "Couldn't finish sending: \(error.localizedDescription)")
    }
  }

  private func fail(_ jobId: String, _ why: String) {
    jobs[jobId]?.phase = .failed
    jobs[jobId]?.problem = why
    save()
    changed()
  }

  private func needSignIn(_ jobId: String) {
    jobs[jobId]?.phase = .signIn
    jobs[jobId]?.problem = "Sign in again to keep sending. Your video is safe on this phone."
    save()
    changed()
  }

  private func retry(_ tag: Tag, status: Int) {
    guard var job = jobs[tag.jobId] else { return }
    guard case .part(let index) = tag.step else { return }
    let tries = (job.attempts[index] ?? 0) + 1
    job.attempts[index] = tries
    jobs[tag.jobId] = job
    save()
    if tries >= SendManager.maxAttempts {
      fail(tag.jobId, "The video couldn't be sent after many tries. Open the app on a good connection to try again.")
      return
    }
    // A short wait while the app is awake; iOS itself paces transfers while it's asleep.
    queue.asyncAfter(deadline: .now() + .seconds(min(tries * 3, 30))) { self.reconcile() }
  }
}

// MARK: Transfer events

extension SendManager: URLSessionTaskDelegate, URLSessionDataDelegate {
  func urlSession(_ session: URLSession, task: URLSessionTask, didSendBodyData bytesSent: Int64,
                  totalBytesSent: Int64, totalBytesExpectedToSend: Int64) {
    guard let tag = Tag(task: task), case .part(let index) = tag.step else { return }
    inFlight[tag.jobId, default: [:]][index] = totalBytesSent
    changed(force: false)
  }

  func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
    guard let tag = Tag(task: task), jobs[tag.jobId] != nil else { return }
    let status = (task.response as? HTTPURLResponse)?.statusCode ?? 0
    let worked = error == nil && (200..<300).contains(status)

    switch tag.step {
    case .part(let index):
      inFlight[tag.jobId]?[index] = nil
      if worked {
        jobs[tag.jobId]?.done.insert(index)
        try? FileManager.default.removeItem(at: partFile(tag.jobId, index))
        save()
        changed()
        if let job = jobs[tag.jobId], job.done.count == job.parts { finish(tag.jobId) }
      } else if (error as? URLError)?.code != .cancelled || jobs[tag.jobId]?.phase == .sending {
        retry(tag, status: status)
      }

    case .size:
      if worked {
        jobs[tag.jobId]?.phase = .sending
        save()
        changed()
        sendMissing(tag.jobId, moving: [])
      } else if status == 401 || status == 403 {
        needSignIn(tag.jobId)
      } else if status == 404 {
        fail(tag.jobId, "The server no longer knows this match. Please film it again.")
      } else {
        queue.asyncAfter(deadline: .now() + .seconds(15)) { self.reconcile() }
      }

    case .complete:
      if worked {
        jobs[tag.jobId]?.phase = .sent
        jobs[tag.jobId]?.problem = nil
        try? FileManager.default.removeItem(at: folder(tag.jobId))
        save()
        changed()
      } else if status == 401 || status == 403 {
        needSignIn(tag.jobId)
      } else if status == 409 || status == 404 {
        fail(tag.jobId, "Some of the video didn't reach the server. Please film it again.")
      } else {
        queue.asyncAfter(deadline: .now() + .seconds(15)) { self.reconcile() }
      }
    }
  }

  func urlSessionDidFinishEvents(forBackgroundURLSession session: URLSession) {
    let done = finishEvents
    finishEvents = nil
    DispatchQueue.main.async { done?() }
  }
}

// What a transfer is for, kept on the transfer so it survives the app being closed.
struct Tag: Hashable {
  enum Step: Hashable {
    case size, complete, part(Int)
    var rawValue: String {
      switch self {
      case .size: return "size"
      case .complete: return "complete"
      case .part(let i): return "part-\(i)"
      }
    }
  }
  let jobId: String
  let step: Step

  init(jobId: String, step: Step) {
    self.jobId = jobId
    self.step = step
  }

  init?(task: URLSessionTask) {
    guard let text = task.taskDescription else { return nil }
    let bits = text.split(separator: "|").map(String.init)
    guard bits.count == 2 else { return nil }
    jobId = bits[0]
    if bits[1] == "size" { step = .size }
    else if bits[1] == "complete" { step = .complete }
    else if bits[1].hasPrefix("part-"), let i = Int(bits[1].dropFirst(5)) { step = .part(i) }
    else { return nil }
  }

  var text: String { "\(jobId)|\(step.rawValue)" }
}

// Asks iOS for a little time to finish a step if the phone locks part way through.
final class BackgroundTime {
  private var id = UIBackgroundTaskIdentifier.invalid

  init() {
    DispatchQueue.main.async {
      self.id = UIApplication.shared.beginBackgroundTask(withName: "AdvantageSend") { self.end() }
    }
  }

  func end() {
    DispatchQueue.main.async {
      guard self.id != .invalid else { return }
      UIApplication.shared.endBackgroundTask(self.id)
      self.id = .invalid
    }
  }
}
