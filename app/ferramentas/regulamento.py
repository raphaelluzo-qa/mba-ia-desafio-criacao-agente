"""Tool de consulta ao regulamento interno (Garantia 4).

O assunto vem da mensagem original da invocação, disponível no ToolContext.
O capítulo solicitado pelo modelo só é aceito se corresponder a esse assunto.
Perguntas sem assunto explícito ou com mais de um assunto exigem esclarecimento,
sem retornar texto do regulamento.
"""

from __future__ import annotations

from google.adk.tools.tool_context import ToolContext

from .. import dados


async def consultar_capitulo_regulamento(capitulo: str, tool_context: ToolContext) -> dict:
    """Consulta somente o capítulo pertinente à mensagem original do morador.

    A seleção do modelo é validada pelo código contra o assunto explícito da
    mensagem que iniciou a invocação. Se a tool pedir esclarecimento, solicite
    ao morador uma pergunta com um único assunto explícito.

    Args:
        capitulo: título do capítulo, por exemplo "Capítulo IV: Piscina".

    Returns:
        Um dicionário com `titulo` e `texto` pertinente, ou um erro sem trechos
        do regulamento quando a seleção não for autorizada.
    """
    conteudo = tool_context.user_content
    pergunta = "\n".join(
        parte.text for parte in (conteudo.parts or []) if parte.text
    ) if conteudo is not None and conteudo.role == "user" else ""
    permitido = dados.capitulo_da_pergunta(pergunta)
    if permitido is None:
        return {
            "erro": "Informe um único assunto explícito para consultar o regulamento.",
            "status": "esclarecimento_necessario",
        }
    solicitado = dados.buscar_capitulo(capitulo)
    if solicitado is None or solicitado.titulo != permitido.titulo:
        return {
            "erro": "O capítulo solicitado não corresponde ao assunto da mensagem.",
            "status": "capitulo_nao_permitido",
            "capitulo_permitido": permitido.titulo,
        }
    return {
        "titulo": permitido.titulo,
        "texto": dados.trecho_do_capitulo(permitido, pergunta),
    }
