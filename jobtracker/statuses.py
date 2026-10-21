"""Application lifecycle statuses and the funnel stage rank each one reaches."""

STATUSES = [
    "discovered", "matched", "shortlisted", "draft_generated", "gmail_draft_created", "applied",
    "employer_replied", "interview_scheduled", "interview_completed", "offer_received",
    "rejected", "withdrawn", "closed", "not_interested",
]

# A job counts at a funnel stage if it EVER reached that rank. Terminal statuses never lower it.
STAGE_RANK = {
    "discovered": 0, "matched": 1, "shortlisted": 2, "draft_generated": 3, "gmail_draft_created": 4,
    "applied": 5, "employer_replied": 6, "interview_scheduled": 7, "interview_completed": 7, "offer_received": 8,
}
TERMINAL = {"rejected", "withdrawn", "closed", "not_interested"}


def rank_of(status: str) -> int | None:
    return STAGE_RANK.get(status)
