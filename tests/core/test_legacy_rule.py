# tests/core/test_legacy_rule.py
"""Fixa os defeitos da regra antiga (epsilon * sigma).

Ela nao existe mais em producao -- foi substituida pelo gate da opcao B.
Volta so para o resampling: a manchete do paper compara as duas regras
sobre os MESMOS dados, e para isso a regra criticada precisa estar
implementada exatamente como era, defeitos inclusos.

Estes testes existem para provar que os defeitos estao presentes. Se um
deles comecar a falhar, a regra 'antiga' deixou de ser a antiga e a
comparacao perde o sentido.
"""
from itertools import permutations

from hefesto.core.gate import legacy_epsilon_sigma_rule, should_promote


def test_legacy_rule_result_depends_on_replica_order():
    # Defeito 1: o pareamento por zip casa replica-i com replica-i. Replicas
    # nao compartilham caso de teste, entao a ordem e arbitraria -- e decide.
    cand = [0.90, 0.60, 0.80, 0.70]
    champ = [0.70, 0.60, 0.75, 0.65]

    outcomes = {legacy_epsilon_sigma_rule(list(p), champ, epsilon=1.0)
                for p in permutations(cand)}

    assert outcomes == {True, False}, "a ordem das replicas deveria mudar o veredito"


def test_legacy_rule_ignores_sample_size():
    # Defeito 2: o limiar e epsilon * sigma, sem n. Replicar o mesmo padrao
    # 10x -- dez vezes mais evidencia -- nao muda nada.
    cand = [0.80, 0.78, 0.82, 0.79]
    champ = [0.75, 0.73, 0.77, 0.74]

    assert (legacy_epsilon_sigma_rule(cand, champ, epsilon=1.0)
            is legacy_epsilon_sigma_rule(cand * 10, champ * 10, epsilon=1.0))


def test_new_rule_does_react_to_sample_size():
    # O contraste: a mesma evidencia replicada muda o veredito do gate novo,
    # porque o erro-padrao encolhe com o n. E o que a regra antiga nao fazia.
    cand = [0.80, 0.70, 0.85, 0.72]
    champ = [0.76, 0.68, 0.80, 0.69]

    assert not should_promote(cand, champ, delta_min=0.0, alpha=0.05)
    assert should_promote(cand * 10, champ * 10, delta_min=0.0, alpha=0.05)


def test_legacy_rule_is_order_invariant_only_by_accident_of_equal_arms():
    # Guarda: com bracos identicos elemento a elemento, todos os deltas sao
    # zero, sigma e zero, e a regra nao promove. Fixa o caso degenerado.
    arm = [0.70, 0.75, 0.72, 0.74]

    assert not legacy_epsilon_sigma_rule(arm, list(arm), epsilon=1.0)
