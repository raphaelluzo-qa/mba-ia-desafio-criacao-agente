"""Leitura dos arquivos estáticos de `dados/`.

Apartamentos, áreas e regulamento não mudam durante a execução, então são lidos
uma vez e mantidos em memória. Reservas e visitantes NÃO são lidos daqui em
tempo de execução: eles vivem no banco (ver `app/armazenamento.py`), porque são
gravados pelo assistente.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache

from . import configuracao


@dataclass(frozen=True)
class Area:
    id: str
    nome: str
    taxa: float

    @property
    def gera_cobranca(self) -> bool:
        """Regra de negócio 2: taxa maior que zero gera cobrança."""
        return self.taxa > 0


@lru_cache(maxsize=1)
def apartamentos() -> dict[str, str]:
    """Mapa `numero -> morador`."""
    bruto = json.loads(configuracao.ARQUIVO_APARTAMENTOS.read_text(encoding="utf-8"))
    return {item["numero"]: item["morador"] for item in bruto}


def apartamento_existe(numero: str) -> bool:
    return numero in apartamentos()


@lru_cache(maxsize=1)
def areas() -> dict[str, Area]:
    """Mapa `id da área -> Area`."""
    bruto = json.loads(configuracao.ARQUIVO_AREAS.read_text(encoding="utf-8"))
    return {item["id"]: Area(id=item["id"], nome=item["nome"], taxa=float(item["taxa"])) for item in bruto}


def reservas_iniciais() -> list[dict]:
    return json.loads(configuracao.ARQUIVO_RESERVAS.read_text(encoding="utf-8"))


def visitantes_iniciais() -> list[dict]:
    return json.loads(configuracao.ARQUIVO_VISITANTES.read_text(encoding="utf-8"))


def _sem_acento(texto: str) -> str:
    normalizado = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in normalizado if not unicodedata.combining(c)).lower()


def resolver_area(termo: str) -> Area | None:
    """Converte o que o morador (ou o modelo) escreveu no id canônico da área.

    Aceita o id (`salao-de-festas`), o nome (`Salão de festas`) ou variações sem
    acento. Devolve `None` quando não reconhece — a tool então recusa em vez de
    inventar uma área.
    """
    alvo = _sem_acento(termo).strip()
    if not alvo:
        return None
    alvo_compacto = re.sub(r"[^a-z0-9]", "", alvo)
    for area in areas().values():
        candidatos = {
            _sem_acento(area.id),
            _sem_acento(area.nome),
            re.sub(r"[^a-z0-9]", "", _sem_acento(area.id)),
            re.sub(r"[^a-z0-9]", "", _sem_acento(area.nome)),
        }
        if alvo in candidatos or alvo_compacto in candidatos:
            return area
    # Busca parcial: "salão" -> "salao-de-festas", "quadra" -> "quadra".
    for area in areas().values():
        nome = _sem_acento(area.nome)
        if alvo and (alvo in nome or nome.startswith(alvo)):
            return area
    return None


DATA_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def data_valida(data: str) -> bool:
    if not DATA_ISO.match(data or ""):
        return False
    from datetime import date

    try:
        date.fromisoformat(data)
    except ValueError:
        return False
    return True


# --------------------------------------------------------------------------
# Regulamento: indexado por capítulo para que o assistente consulte um capítulo
# por vez em vez de carregar o documento inteiro (Garantia 4).
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Capitulo:
    titulo: str
    texto: str


@lru_cache(maxsize=1)
def capitulos_regulamento() -> list[Capitulo]:
    texto = configuracao.ARQUIVO_REGULAMENTO.read_text(encoding="utf-8")
    partes = re.split(r"^## ", texto, flags=re.MULTILINE)[1:]
    capitulos: list[Capitulo] = []
    for parte in partes:
        linhas = parte.splitlines()
        titulo = linhas[0].strip()
        capitulos.append(Capitulo(titulo=titulo, texto=("## " + parte).strip()))
    return capitulos


def indice_regulamento() -> list[str]:
    """Só os títulos dos capítulos — nenhum conteúdo."""
    return [c.titulo for c in capitulos_regulamento()]


def buscar_capitulo(termo: str) -> Capitulo | None:
    """Localiza um capítulo pelo título, pelo número romano ou por palavra-chave."""
    alvo = _sem_acento(termo).strip()
    if not alvo:
        return None
    for capitulo in capitulos_regulamento():
        if _sem_acento(capitulo.titulo) == alvo:
            return capitulo
    for capitulo in capitulos_regulamento():
        if alvo in _sem_acento(capitulo.titulo):
            return capitulo
    # Última tentativa: alguma palavra do pedido aparece no título do capítulo.
    palavras = [p for p in re.split(r"[^a-z0-9]+", alvo) if len(p) > 3]
    melhor: tuple[int, Capitulo] | None = None
    for capitulo in capitulos_regulamento():
        titulo = _sem_acento(capitulo.titulo)
        pontos = sum(1 for p in palavras if p in titulo)
        if pontos and (melhor is None or pontos > melhor[0]):
            melhor = (pontos, capitulo)
    return melhor[1] if melhor else None


# A selecao usa a mensagem original da invocacao, nunca um assunto do modelo.
_ASSUNTOS_REGULAMENTO = {
    "I": r"\b(disposicoes gerais|convencao|sindico|administracao|aplicativo|trabalho remoto)\b",
    "II": r"\b(direitos|deveres|obrigacoes|fachada|varanda|sacada)\b",
    "III": r"\b(silencio|barulho|ruido|sossego|som alto|musica alta)\b",
    "IV": r"\b(piscina|piscinas|natacao|nadar|deck)\b",
    "V": r"\b(academia|brinquedoteca|playground)\b",
    "VI": r"\b(salao|churrasqueira|quadra)\b",
    "VII": r"\b(portaria|seguranca|visitante|visitantes|entregador|entregadores|delivery)\b",
    "VIII": r"\b(animais|animal|pet|pets|cachorro|cachorros|gato|gatos)\b",
    "IX": r"\b(mudanca|mudancas)\b",
    "X": r"\b(obra|obras|reforma|reformas)\b",
    "XI": r"\b(garagem|garagens|veiculo|veiculos|carro|carros|vaga|vagas|estacionamento)\b",
    "XII": r"\b(lixo|reciclagem|residuo|residuos|coleta)\b",
    "XIII": r"\b(infracao|infracoes|penalidade|penalidades|multa|multas|advertencia|recurso)\b",
    "XIV": r"\b(disposicoes finais|vigencia|alteracao do regulamento)\b",
}


def capitulo_da_pergunta(pergunta: str) -> Capitulo | None:
    """Resolve um unico assunto explicito; perguntas ambiguas exigem esclarecimento."""
    normalizada = _sem_acento(pergunta)
    assuntos = [
        numero
        for numero, padrao in _ASSUNTOS_REGULAMENTO.items()
        if re.search(padrao, normalizada)
    ]
    if len(assuntos) != 1:
        return None
    prefixo = f"capitulo {assuntos[0].lower()}:"
    return next(
        (c for c in capitulos_regulamento() if _sem_acento(c.titulo).startswith(prefixo)),
        None,
    )


def trecho_do_capitulo(capitulo: Capitulo, pergunta: str) -> str:
    """Recorta artigos completos do capitulo autorizado, sem buscar em outros."""
    artigos = re.split(r"(?=^\*\*Art\. )", capitulo.texto, flags=re.MULTILINE)[1:]
    palavras_titulo = set(re.findall(r"[a-z0-9]+", _sem_acento(capitulo.titulo)))
    ignoradas = palavras_titulo | {
        "quais", "qual", "como", "sobre", "regras", "regra", "normas", "norma",
        "regulamento", "interno", "condominio", "posso", "pode", "para", "pela",
        "pelo", "esse", "essa", "este", "esta", "funciona",
    }
    palavras = {
        p for p in re.findall(r"[a-z0-9]+", _sem_acento(pergunta))
        if len(p) > 3 and p not in ignoradas
    }
    if palavras & {"horas", "horario", "horarios", "fecha", "fechar", "abre", "abrir"}:
        palavras.update({"periodos", "horario", "horarios", "funciona"})
    selecionados = [
        artigo.strip() for artigo in artigos
        if palavras & set(re.findall(r"[a-z0-9]+", _sem_acento(artigo)))
    ]
    # Perguntas gerais sobre um assunto recebem apenas o respectivo capitulo.
    return "\n\n".join(selecionados) if selecionados else capitulo.texto
