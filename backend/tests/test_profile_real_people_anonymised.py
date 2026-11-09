"""Real individual people are simulated as anonymous roles, never under their real names.

Owner's rule (2026-11-09), after an Irish vape-pricing run simulated named TDs ("Holly Cairns",
"Jack Chambers (Politician)") and the report quoted and characterised them. Organisations keep
their real names.
"""

import json
from unittest.mock import MagicMock, patch

from app.services.oasis_profile_generator import OasisProfileGenerator
from app.services.zep_entity_reader import EntityNode


def _entity(name: str, entity_type: str, summary: str = "") -> EntityNode:
    return EntityNode(
        uuid=f"uuid-{abs(hash(name))}", name=name, labels=["Entity", entity_type], summary=summary, attributes={}
    )


def _llm_response(payload: dict) -> MagicMock:
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = json.dumps(payload)
    resp.choices[0].finish_reason = "stop"
    return resp


def _generator() -> OasisProfileGenerator:
    gen = OasisProfileGenerator(api_key="test-key", base_url="http://localhost", model_name="m")
    gen.client = MagicMock()
    return gen


def _all_text(profile) -> str:
    return json.dumps(profile.to_dict(), ensure_ascii=False).lower()


@patch.object(OasisProfileGenerator, "_search_zep_for_entity", return_value={})
def test_llm_persona_for_real_person_uses_role_not_name(_search):
    gen = _generator()
    # The LLM ignores the instruction and names her anyway; the result must still not.
    gen.client.chat.completions.create.return_value = _llm_response(
        {
            "role_label": "An opposition TD",
            "bio": "Holly Cairns, TD. Fighting for rural Ireland.",
            "persona": "Holly Cairns leads her party. Cairns often criticises the Government.",
            "age": 35,
            "gender": "female",
            "profession": "TD (Holly Cairns's office)",
            "interested_topics": ["Public health", "Cairns campaign"],
        }
    )

    profile = gen.generate_profile_from_entity(
        _entity("Holly Cairns", "Person", "Holly Cairns is a Social Democrats TD."), user_id=0
    )

    assert profile.name == "An opposition TD"
    assert "holly" not in _all_text(profile) and "cairns" not in _all_text(profile)
    assert "the opposition TD often criticises the Government" in profile.persona
    for row in (profile.to_reddit_format(), profile.to_twitter_format()):
        assert "cairns" not in json.dumps(row).lower()

    prompt = gen.client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
    assert "role_label" in prompt and "never output it" in prompt


@patch.object(OasisProfileGenerator, "_search_zep_for_entity", return_value={})
def test_role_label_that_names_the_person_is_replaced_by_the_entity_type(_search):
    gen = _generator()
    gen.client.chat.completions.create.return_value = _llm_response(
        {"role_label": "Jack Chambers, Minister", "bio": "Minister.", "persona": "A minister."}
    )

    profile = gen.generate_profile_from_entity(_entity("Jack Chambers (Politician)", "GovernmentMinister"), user_id=1)

    assert profile.name == "A government minister"
    assert "chambers" not in _all_text(profile) and "jack" not in _all_text(profile)


@patch.object(OasisProfileGenerator, "_search_zep_for_entity", return_value={})
def test_batch_anonymises_people_on_profiles_and_entities_but_keeps_organisations(_search):
    gen = _generator()
    entities = [
        _entity("Holly Cairns", "Person", "Holly Cairns opposes the minimum price."),
        _entity("Mary Murphy", "Person", "Mary Murphy runs a vape shop."),
        _entity("Revolut", "Company", "Revolut launched Revolut Mobile in Ireland."),
    ]

    profiles = gen.generate_profiles_from_entities(entities, use_llm=False, parallel_count=1)

    assert [p.name for p in profiles] == ["A person", "A person (2)", "Revolut"]
    for p in profiles[:2]:
        text = _all_text(p)
        assert "holly" not in text and "cairns" not in text and "murphy" not in text
    # The config generator reads these same entities next; its entity_name feeds every action log.
    assert [e.name for e in entities] == ["A person", "A person (2)", "Revolut"]
    assert "Cairns" not in entities[0].summary
    assert entities[2].summary == "Revolut launched Revolut Mobile in Ireland."


def test_person_types_are_recognised_by_head_noun_and_organisations_are_not():
    gen = _generator()
    for person_type in ("Person", "Politician", "OppositionTD", "GovernmentMinister", "PublicFigure", "CEO"):
        assert gen._is_individual_entity(person_type), person_type
    for org_type in ("Company", "Organization", "GovernmentDepartment", "MediaOutlet", "PolicyInstitute", "Regulator"):
        assert not gen._is_individual_entity(org_type), org_type
