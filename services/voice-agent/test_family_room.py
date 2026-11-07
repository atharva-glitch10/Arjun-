"""Arjun stays quiet while a family member is in the room."""

from familyroom import FamilyPresence


def test_with_no_family_arjun_may_speak():
    family = FamilyPresence()
    assert not family.present()
    assert not family.quiet(False)


def test_a_family_participant_keeps_arjun_quiet():
    family = FamilyPresence()
    family.joined("family")
    assert family.present()
    assert family.quiet(False)


def test_the_elder_and_the_agent_are_not_family():
    family = FamilyPresence()
    family.joined("elder-1")
    family.joined("agent")
    assert not family.present()


def test_when_the_family_leaves_arjun_can_speak_again():
    family = FamilyPresence()
    family.joined("family")
    family.left("family")
    assert not family.present()
    assert not family.quiet(False)


def test_a_locked_speech_lock_still_counts_as_quiet():
    assert FamilyPresence().quiet(True)


def test_an_unknown_identity_leaving_does_not_clear_the_family():
    family = FamilyPresence()
    family.joined("family")
    family.left("elder-1")
    assert family.present()


def test_family_presence_allows_safety_words_only():
    family = FamilyPresence()
    family.joined("family")
    assert family.should_process("छातीत दुखतंय")
    assert not family.should_process("आज काय आहे")
    assert not family.should_process("बंद कर")
