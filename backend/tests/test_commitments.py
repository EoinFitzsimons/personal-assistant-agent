from app.pipeline.commitments import INBOX_THRESHOLD, detect, prefilter_commitments
from tests.helpers import demo_data


def _by_title(cands, needle):
    return [c for c in cands if needle.lower() in c.title.lower()]


def test_prefilter_only_users_own_messages_with_will_phrases():
    items = demo_data().items
    pre = prefilter_commitments(items)
    assert all(i.author_is_me for i in pre)
    assert {"s2", "s4", "s6", "s7", "m2", "e4"} <= {i.id for i in pre}


def test_detects_real_commitments_with_owner_and_deadline():
    cands = detect(demo_data().items, "Anastasiia")
    deck = _by_title(cands, "Q3 metrics deck")
    assert len(deck) == 1
    assert deck[0].title.startswith("Send the Q3 metrics deck")
    assert deck[0].kind == "commitment"
    assert deck[0].owed_to == "Sarah Chen"
    assert deck[0].due_soon
    assert deck[0].confidence >= INBOX_THRESHOLD
    legal = _by_title(cands, "check with legal")
    assert legal and legal[0].owed_to == "Priya Nair"
    hiring = _by_title(cands, "hiring plan")
    assert hiring and hiring[0].owed_to == "Sarah Chen"


def test_drops_completed_commitments_and_noise():
    cands = detect(demo_data().items, "Anastasiia")
    assert not _by_title(cands, "review it")
    assert not _by_title(cands, "raining")


def test_ambiguous_commitment_goes_below_inbox_threshold():
    cands = detect(demo_data().items, "Anastasiia")
    writeup = [c for c in cands if "write-up" in c.details]
    assert writeup and writeup[0].confidence < INBOX_THRESHOLD


def test_follow_up_only_for_unanswered_requests():
    cands = detect(demo_data().items, "Anastasiia")
    follow = [c for c in cands if c.kind == "follow_up"]
    owners = {c.owed_to for c in follow}
    assert "Mark Rivera (Acme Corp)" in owners
    assert "Lena Fischer" not in owners  # already answered
    assert "Sarah Chen" not in owners  # covered by the commitment
    assert "Priya Nair" not in owners
