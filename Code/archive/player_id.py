"""
Resolves raw ByteTrack IDs into consistent Player 1 / Player 2 labels
using K-means clustering on each track's mean horizontal pixel position
(players occupy opposite halves of the frame).

Ported from ping pong as-is (Day 2). This logic is sport-agnostic — it
only depends on track_id / pixel_x, not table or court geometry — so per
PROJECT.md's player-tracking TODO it's expected to transfer directly with
no rework. NOT YET TESTED on real tennis footage; validate once footage
lands (blocked on camera angle confirmation, see PROJECT.md risks).

Run this standalone after transform.py:
    python player_id.py

NOTE (known limitation, inherited from ping pong): this assumes players
never swap sides mid-video. Tennis players DO swap sides between sets/on
odd games in a full match — if dev/validation footage includes an end
change, this clustering will mislabel the players after the swap. Flagging
here since it's more likely to actually occur in tennis than it was in
ping pong; not fixing preemptively since MVP footage may not cover a full
match with a side change.
"""

import pandas as pd
from sklearn.cluster import KMeans

import config


def assign_player_ids(match_csv_path):
    """
    Loads match_csv_path, clusters player track IDs into 2 groups by mean
    pixel_x, assigns Player 1 to the left-side cluster and Player 2 to the
    right-side cluster, and overwrites match_csv_path with the cleaned data.

    Returns
    -------
    pd.DataFrame
        The final dataframe with resolved player IDs.
    """
    df = pd.read_csv(match_csv_path)
    player_df = df[df["type"] == "player"].copy()

    # Mean pixel_x per track ID — players occupy opposite horizontal halves.
    id_positions = (
        player_df.groupby("track_id")["pixel_x"]
        .mean()
        .dropna()
        .reset_index()
    )
    id_positions.columns = ["track_id", "mean_x"]

    print(f"Clustering {len(id_positions)} track IDs into 2 players...")

    if len(id_positions) < 2:
        raise RuntimeError(
            f"Only {len(id_positions)} player track ID(s) found — need at least 2 "
            f"to cluster into Player 1 / Player 2. Check player detection quality."
        )

    kmeans = KMeans(n_clusters=2, random_state=42, n_init=10)
    id_positions["cluster"] = kmeans.fit_predict(id_positions[["mean_x"]])

    centers = kmeans.cluster_centers_.flatten()
    left_cluster = int(centers.argmin())    # smaller x = left side = Player 1
    right_cluster = int(centers.argmax())   # larger x  = right side = Player 2

    id_positions["real_player_id"] = id_positions["cluster"].apply(
        lambda c: 1 if c == left_cluster else 2
    )

    print("\nCluster centers (mean pixel_x):")
    print(f"  Player 1 side: x = {centers[left_cluster]:.0f}px")
    print(f"  Player 2 side: x = {centers[right_cluster]:.0f}px")

    p1_ids = id_positions[id_positions["real_player_id"] == 1]["track_id"].tolist()
    p2_ids = id_positions[id_positions["real_player_id"] == 2]["track_id"].tolist()
    print(f"\n  {len(p1_ids)} track IDs → Player 1")
    print(f"  {len(p2_ids)} track IDs → Player 2")

    id_map = dict(zip(id_positions["track_id"], id_positions["real_player_id"]))
    player_df["track_id"] = player_df["track_id"].map(id_map)

    ball_df = df[df["type"] == "ball"].copy()
    final_df = pd.concat([ball_df, player_df]).sort_values(["frame", "type"]).reset_index(drop=True)

    final_df.to_csv(match_csv_path, index=False)

    player_check = final_df[final_df["type"] == "player"]
    print("\n── After cleanup ─────────────────────────────────────────────────────")
    print(f"  Unique player IDs: {sorted(player_check['track_id'].dropna().unique().astype(int))}")
    print(f"  Player 1 detections: {len(player_check[player_check['track_id'] == 1])}")
    print(f"  Player 2 detections: {len(player_check[player_check['track_id'] == 2])}")
    print(f"\nSaved cleaned {match_csv_path}")

    return final_df


if __name__ == "__main__":
    assign_player_ids(config.MATCH_CSV)
