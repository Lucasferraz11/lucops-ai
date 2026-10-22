"""Small replaceable provider contract and deterministic offline implementation."""

from dataclasses import dataclass
from typing import Protocol

from .schemas import (
    Evidence,
    Hypothesis,
    InvestigationContext,
    InvestigationDraft,
    MLStatus,
    Recommendation,
)
from .tools import BatchSummary, DuplicateMatches


@dataclass(frozen=True)
class InvestigationInput:
    """Only server-built, minimized information; never the original CSV."""

    context: InvestigationContext
    evidence: tuple[Evidence, ...]
    duplicates: DuplicateMatches
    batch_summary: BatchSummary


class InvestigationProvider(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def mode(self) -> str: ...

    def generate(self, investigation: InvestigationInput) -> InvestigationDraft: ...


class SimulatedProvider:
    """Fixed templates, no randomness, external calls, or generated facts."""

    name = "deterministic-rules-v1"
    mode = "simulated"

    def generate(self, investigation: InvestigationInput) -> InvestigationDraft:
        context = investigation.context
        hypotheses = []
        recommendations = []
        insufficient = [
            "As evidências disponíveis não permitem confirmar a causa nem atribuir responsabilidade."
        ]

        for issue in context.inconsistencies:
            if issue.field == "id_transacao" and issue.message == "Duplicate value.":
                continue  # The duplicate tool also covers the first occurrence.
            references = (issue.evidence_id,)
            if issue.field == "valor":
                hypotheses.append(
                    Hypothesis(
                        "O valor pode ter sido informado em formato ou quantia incompatível "
                        "com as regras financeiras; sua origem não foi confirmada.",
                        references,
                    )
                )
                recommendations.append(
                    Recommendation(
                        "Compare o valor com o registro de origem e a regra não atendida "
                        "antes de propor uma correção.",
                        references,
                    )
                )
            else:
                hypotheses.append(
                    Hypothesis(
                        "O registro pode conter a omissão de um campo obrigatório; "
                        "a etapa responsável não foi identificada.",
                        references,
                    )
                )
                recommendations.append(
                    Recommendation(
                        "Confira o campo obrigatório no registro de origem; não preencha "
                        "identificadores de cliente ou transação por suposição.",
                        references,
                    )
                )

        if investigation.duplicates.related_record_indices:
            references = tuple(
                evidence.evidence_id
                for evidence in investigation.evidence
                if evidence.source.function == "lucops.agents.tools.find_duplicates"
                and evidence.source.field == "id_transacao"
            )
            hypotheses.append(
                Hypothesis(
                    "Identificadores repetidos podem indicar reenvio ou eventos distintos "
                    "com a mesma chave; o CSV atual não confirma nenhuma dessas causas.",
                    references,
                )
            )
            recommendations.append(
                Recommendation(
                    "Compare os registros relacionados e os identificadores dos eventos "
                    "na origem antes de decidir sobre correção ou remoção.",
                    references,
                )
            )

        ml_status_reference = tuple(
            evidence.evidence_id
            for evidence in investigation.evidence
            if evidence.source.function == "lucops.agents.tools.get_ml_information"
            and evidence.source.field == "ml.status"
        )
        if context.ml.status == MLStatus.EVALUATED and context.ml.is_anomaly:
            hypotheses.append(
                Hypothesis(
                    "O valor pode ser atípico em relação ao padrão aprendido; "
                    "não há justificativa de negócio disponível.",
                    context.ml.evidence_ids,
                )
            )
            recommendations.append(
                Recommendation(
                    "Revise a transação de origem e obtenha contexto de negócio para o "
                    "alerta estatístico. A pontuação não é probabilidade de fraude.",
                    context.ml.evidence_ids,
                )
            )
        elif context.ml.status == MLStatus.UNAVAILABLE:
            insufficient.append(
                "A avaliação de ML está indisponível; a ausência de pontuação não "
                "demonstra ausência de anomalia estatística."
            )
            recommendations.append(
                Recommendation(
                    "Solicite avaliação de ML quando houver modelo compatível configurado.",
                    ml_status_reference,
                )
            )
        elif context.ml.status == MLStatus.INELIGIBLE:
            insufficient.append(
                "O comportamento estatístico não pode ser avaliado enquanto o registro "
                "for inelegível para ML."
            )
            recommendations.append(
                Recommendation(
                    "Revise os motivos de inelegibilidade antes de solicitar inferência de ML.",
                    ml_status_reference,
                )
            )
        elif (
            not context.inconsistencies
            and not investigation.duplicates.related_record_indices
        ):
            insufficient.append(
                "As verificações disponíveis não identificaram problemas de qualidade "
                "nem alerta de ML neste registro; isso não exclui outros problemas de negócio."
            )

        return InvestigationDraft(
            hypotheses=tuple(hypotheses),
            recommendations=tuple(recommendations),
            limitations=(
                "Sugestões simuladas não são explicações comprovadas de causas de negócio.",
            ),
            insufficient_evidence=tuple(insufficient),
        )


def select_provider(mode: str) -> InvestigationProvider:
    """Select a provider explicitly; importing the optional SDK is deferred."""
    if mode == "simulated":
        return SimulatedProvider()
    if mode == "openai":
        from .openai_provider import OpenAIProvider

        return OpenAIProvider()
    raise ValueError("Provider must be 'simulated' or 'openai'.")
