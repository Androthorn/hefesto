from hefesto.store.repository import Repository


def test_persists_prompt_and_refinements(tmp_path):
    repo = Repository(db_path=str(tmp_path / "h.db"))
    repo.init_db()
    repo.save_prompt(name="p", version="v1", prompt_text="hello")
    repo.save_refinement(
        parent_version="v1", candidate_version="v2",
        promoted=False, delta=-0.1, reason="no_improvement",
    )
    repo.save_refinement(
        parent_version="v1", candidate_version="v3",
        promoted=True, delta=0.2, reason="promoted",
    )
    refs = repo.get_refinements()
    assert len(refs) == 2
    assert {r.promoted for r in refs} == {True, False}  # rejected attempts persisted


def test_saves_evaluation_with_agreement(tmp_path):
    repo = Repository(db_path=str(tmp_path / "h.db"))
    repo.init_db()
    repo.save_evaluation(prompt_version="v1", composite_score=0.7,
                         metrics={"clarity": 0.7}, judge_agreement=0.82)
    ev = repo.get_evaluations()
    assert ev[0].composite_score == 0.7 and ev[0].judge_agreement == 0.82
