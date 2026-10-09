"""
run_scoring_chain.py

Chains player_identity.py -> rally_outcomes.py -> scoring.py against the
real match_data.csv / rally_events.csv, and writes the results to CSV so
they can be inspected directly (none of these three modules write output
on their own when called this way -- they just return DataFrames/dicts).

Run from the same directory as the other pipeline modules (or adjust the
imports below to match your layout).
"""

import pandas as pd

import config
import player_identity as pi
import rally_outcomes as ro
import scoring as sc

OUT_QA = "identity_qa.csv"
OUT_PER_POINT = "scored_points.csv"


def main():
    match_data_df = pd.read_csv(config.MATCH_CSV)
    events_df = pd.read_csv(config.EVENTS_CSV)

    labels, qa_df = pi.compute_rally_near_far_labels(match_data_df, events_df)
    qa_df.to_csv(OUT_QA, index=False)
    print(f"Resolved near/far for {len(labels)}/{len(qa_df)} rallies -> {OUT_QA}")

    outcomes_df = ro.rally_outcomes(events_df)
    relabeled = pi.relabel_outcomes_to_near_far(outcomes_df, labels)

    per_point_df, summary = sc.score_match_near_far(relabeled)
    per_point_df.to_csv(OUT_PER_POINT, index=False)

    print(f"\n--- Match summary ---")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    print(f"\nPer-point detail -> {OUT_PER_POINT}")

    # Sanity check for the player_identity.py vs detect_hits() fix:
    # rally 22 (or whichever rally your qa_df flags as
    # hit_attribution_disagreement_unresolvable) should show up in
    # per_point_df with scored=False, not a guessed winner.
    unresolved_qa = qa_df[~qa_df["resolved"]]
    if len(unresolved_qa):
        print(f"\nUnresolved-identity rallies (qa_df):\n{unresolved_qa.to_string(index=False)}")


if __name__ == "__main__":
    main()
