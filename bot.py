import logging
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo
import random
import re
import unicodedata

from dotenv import load_dotenv
from supabase import Client, create_client

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)


# ============================================================
# Configurações
# ============================================================

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("A variável TELEGRAM_BOT_TOKEN não foi definida.")

if not SUPABASE_URL:
    raise RuntimeError("A variável SUPABASE_URL não foi definida.")

if not SUPABASE_SERVICE_ROLE_KEY:
    raise RuntimeError(
        "A variável SUPABASE_SERVICE_ROLE_KEY não foi definida."
    )

supabase: Client = create_client(
    SUPABASE_URL,
    SUPABASE_SERVICE_ROLE_KEY,
)

FUSO_HORARIO = ZoneInfo("America/Sao_Paulo")

# Estado usado pela ConversationHandler
AGUARDANDO_VALOR = 1
AGUARDANDO_NOME = 2


# ============================================================
# Logging
# ============================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


# ============================================================
# Tipos de registro
# ============================================================

TIPOS_REGISTRO = {
    "medicamento": "Medicamento administrado",
    "dor": "Dor",
    "alimentacao": "Alimentação",
    "hidratacao": "Hidratação",
    "sono": "Sono",
    "humor": "Humor / Comportamento",
    "queda": "Queda",
    "sintoma": "Sintoma / Intercorrência",
    "observacao": "Observação livre",
}


# ============================================================
# Funções auxiliares de banco
# ============================================================

def buscar_primeiro(query):
    """
    Executa uma consulta Supabase e retorna o primeiro item encontrado.
    """
    resposta = query.limit(1).execute()

    if resposta.data:
        return resposta.data[0]

    return None


def obter_usuario_nome(update: Update) -> str:
    """
    Obtém um nome amigável do usuário do Telegram.
    """
    user = update.effective_user

    if not user:
        return "Usuário desconhecido"

    partes = []

    if user.first_name:
        partes.append(user.first_name)

    if user.last_name:
        partes.append(user.last_name)

    nome = " ".join(partes).strip()

    if nome:
        return nome

    if user.username:
        return f"@{user.username}"

    return str(user.id)


def obter_sessao_atual(user_id: int) -> Optional[dict]:
    """
    Retorna o idoso atualmente selecionado pelo usuário.
    """
    resposta = (
        supabase
        .table("sessoes_ativas")
        .select("user_id, codigo_idoso")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )

    if resposta.data:
        return resposta.data[0]

    return None


def obter_codigo_atual(user_id: int) -> Optional[str]:
    """
    Retorna o código do idoso atualmente selecionado.
    """
    sessao = obter_sessao_atual(user_id)

    if not sessao:
        return None

    return sessao["codigo_idoso"]


def formatar_data(data_texto: str) -> str:
    """
    Converte a data do banco para o formato brasileiro.
    """
    try:
        data_texto = data_texto.replace("Z", "+00:00")
        data = datetime.fromisoformat(data_texto)

        if data.tzinfo is None:
            data = data.replace(tzinfo=timezone.utc)

        data = data.astimezone(FUSO_HORARIO)

        return data.strftime("%d/%m/%Y %H:%M")

    except Exception:
        return data_texto


def quebrar_mensagem(texto: str, limite: int = 3900) -> list[str]:
    """
    Divide mensagens longas para respeitar o limite do Telegram.
    """
    partes = []

    while len(texto) > limite:
        posicao = texto.rfind("\n", 0, limite)

        if posicao == -1:
            posicao = limite

        partes.append(texto[:posicao])
        texto = texto[posicao:].lstrip("\n")

    if texto:
        partes.append(texto)

    return partes


# ============================================================
# Teclados
# ============================================================

def teclado_principal() -> InlineKeyboardMarkup:
    """
    Menu principal do bot.
    """
    teclado = [
        [
            InlineKeyboardButton(
                "💊 Medicamento administrado",
                callback_data="registro:medicamento",
            )
        ],
        [
            InlineKeyboardButton(
                "🩹 Dor",
                callback_data="registro:dor",
            ),
            InlineKeyboardButton(
                "🍽 Alimentação",
                callback_data="registro:alimentacao",
            ),
        ],
        [
            InlineKeyboardButton(
                "💧 Hidratação",
                callback_data="registro:hidratacao",
            ),
            InlineKeyboardButton(
                "😴 Sono",
                callback_data="registro:sono",
            ),
        ],
        [
            InlineKeyboardButton(
                "🙂 Humor / Comportamento",
                callback_data="registro:humor",
            )
        ],
        [
            InlineKeyboardButton(
                "⚠️ Queda",
                callback_data="registro:queda",
            ),
            InlineKeyboardButton(
                "🩺 Sintoma / Intercorrência",
                callback_data="registro:sintoma",
            ),
        ],
        [
            InlineKeyboardButton(
                "📝 Observação livre",
                callback_data="registro:observacao",
            )
        ],
        [
            InlineKeyboardButton(
                "📅 Ver hoje",
                callback_data="ver:hoje",
            )
        ],
        [
            InlineKeyboardButton(
                "📊 Resumo 7 dias",
                callback_data="resumo:7",
            ),
            InlineKeyboardButton(
                "📊 Resumo 14 dias",
                callback_data="resumo:14",
            ),
        ],
        [
            InlineKeyboardButton(
                "🚪 Sair deste idoso",
                callback_data="acao:sair",
            )
        ],
    ]

    return InlineKeyboardMarkup(teclado)


def teclado_voltar() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "⬅️ Voltar ao menu",
                    callback_data="acao:menu",
                )
            ]
        ]
    )


# ============================================================
# Formatação de mensagens
# ============================================================

def texto_boas_vindas() -> str:
    return (
        "Olá! Eu sou o Cuidar+.\n\n"
        "Este bot ajuda cuidadores a registrar e acompanhar informações "
        "do cuidado cotidiano de uma pessoa idosa.\n\n"
        "Como começar:\n"
        "1. Se o idoso já foi cadastrado, entre com /entrar CODIGO.\n"
        "   Exemplo: /entrar MARIA78\n"
        "2. Se ainda não foi, cadastre com /novoidoso.\n"
        "3. Escolha uma opção no menu e digite a informação solicitada.\n\n"
        "Comandos disponíveis:\n"
        "/start - Mostrar esta mensagem\n"
        "/novoidoso - Cadastrar um novo idoso\n"
        "/entrar CODIGO - Entrar no cuidado de um idoso\n"
        "/sair - Sair do idoso atual\n"
        "/hoje - Ver os registros de hoje\n"
        "/meusidosos - Ver os idosos aos quais você está vinculado\n"
        "/cancelar - Cancelar o que estiver fazendo"
    )


async def enviar_menu(update: Update, codigo: str) -> None:
    mensagem = (
        f"Você está no cuidado do idoso de código {codigo}.\n\n"
        "Escolha uma opção para registrar ou consultar informações:"
    )

    if update.callback_query:
        await update.callback_query.message.reply_text(
            mensagem,
            reply_markup=teclado_principal(),
        )
    elif update.message:
        await update.message.reply_text(
            mensagem,
            reply_markup=teclado_principal(),
        )


# ============================================================
# Comandos
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    teclado = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "➕ Cadastrar novo idoso",
                    callback_data="acao:novoidoso",
                )
            ]
        ]
    )

    await update.message.reply_text(
        texto_boas_vindas(),
        reply_markup=teclado,
    )


async def entrar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return

    if not context.args:
        await update.message.reply_text(
            "Informe o código do idoso.\n\n"
            "Exemplo:\n"
            "/entrar MARIA78"
        )
        return

    codigo = context.args[0].strip().upper()
    user_id = update.effective_user.id
    nome_usuario = obter_usuario_nome(update)

    try:
        idoso = buscar_primeiro(
            supabase
            .table("idosos")
            .select("codigo, nome")
            .eq("codigo", codigo)
        )

        if not idoso:
            await update.message.reply_text(
                f"Não encontrei nenhum idoso com o código {codigo}.\n"
                "Confira o código e tente novamente."
            )
            return

        # Registra o vínculo do usuário com o idoso.
        supabase.table("vinculos_cuidadores").upsert(
            {
                "user_id": user_id,
                "user_name": nome_usuario,
                "codigo_idoso": codigo,
            },
            on_conflict="user_id,codigo_idoso",
        ).execute()

        # Define esse idoso como o idoso atual do usuário.
        supabase.table("sessoes_ativas").upsert(
            {
                "user_id": user_id,
                "codigo_idoso": codigo,
            },
            on_conflict="user_id",
        ).execute()

        nome_idoso = idoso.get("nome") or "não informado"

        await update.message.reply_text(
            f"Você entrou no cuidado de {nome_idoso}.\n"
            f"Código: {codigo}\n\n"
            "Agora todos os registros feitos por você serão associados "
            "a esse idoso.",
            reply_markup=teclado_principal(),
        )

    except Exception:
        logger.exception("Erro ao processar /entrar")

        await update.message.reply_text(
            "Ocorreu um erro ao entrar no cuidado. "
            "Tente novamente em alguns instantes."
        )


async def sair(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id

    try:
        sessao = obter_sessao_atual(user_id)

        if not sessao:
            await update.message.reply_text(
                "Você não está conectado a nenhum idoso no momento."
            )
            return

        supabase.table("sessoes_ativas").delete().eq(
            "user_id", user_id
        ).execute()

        await update.message.reply_text(
            "Você saiu do cuidado atual. "
            "Os registros já realizados continuam salvos."
        )

    except Exception:
        logger.exception("Erro ao processar /sair")

        await update.message.reply_text(
            "Não foi possível sair do cuidado agora. "
            "Tente novamente."
        )


async def meus_idosos(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id

    try:
        resposta = (
            supabase
            .table("vinculos_cuidadores")
            .select("codigo_idoso, idosos(nome)")
            .eq("user_id", user_id)
            .order("joined_at", desc=True)
            .execute()
        )

        if not resposta.data:
            await update.message.reply_text(
                "Você ainda não está vinculado a nenhum idoso."
            )
            return

        linhas = ["Idosos aos quais você está vinculado:\n"]

        for item in resposta.data:
            codigo = item["codigo_idoso"]
            dados_idoso = item.get("idosos") or {}
            nome = dados_idoso.get("nome") or "nome não informado"

            linhas.append(f"• {nome} — código {codigo}")

        await update.message.reply_text("\n".join(linhas))

    except Exception:
        logger.exception("Erro ao processar /meusidosos")

        await update.message.reply_text(
            "Não foi possível consultar seus vínculos agora."
        )


# ============================================================
# Registros
# ============================================================

async def iniciar_registro(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    query = update.callback_query
    await query.answer()

    if not update.effective_user:
        return ConversationHandler.END

    codigo = obter_codigo_atual(update.effective_user.id)

    if not codigo:
        await query.message.reply_text(
            "Você não está conectado a nenhum idoso. "
            "Use /entrar CODIGO antes de registrar informações."
        )
        return ConversationHandler.END

    chave = query.data.split(":", 1)[1]
    tipo = TIPOS_REGISTRO.get(chave)

    if not tipo:
        await query.message.reply_text(
            "Tipo de registro inválido."
        )
        return ConversationHandler.END

    context.user_data["tipo_registro"] = tipo
    context.user_data["chave_registro"] = chave

    if chave == "dor":
        instrucoes = (
            "Informe a intensidade da dor usando um número de 0 a 10.\n"
            "Exemplo: 7"
        )
    elif chave == "queda":
        instrucoes = (
            "Descreva a queda: informe, se possível, quando ocorreu, "
            "como aconteceu e se houve ferimentos."
        )
    elif chave == "medicamento":
        instrucoes = (
            "Informe o medicamento administrado, a dose e, se quiser, "
            "o horário.\n"
            "Exemplo: Dipirona 500 mg, às 14h"
        )
    elif chave == "alimentacao":
        instrucoes = (
            "Descreva a alimentação realizada e, se possível, a quantidade.\n"
            "Exemplo: Almoçou metade do prato e tomou suco."
        )
    elif chave == "hidratacao":
        instrucoes = (
            "Informe a quantidade aproximada de líquidos ingeridos.\n"
            "Exemplo: Tomou 3 copos de água."
        )
    elif chave == "sono":
        instrucoes = (
            "Descreva como foi o sono.\n"
            "Exemplo: Dormiu bem durante 7 horas."
        )
    elif chave == "humor":
        instrucoes = (
            "Descreva o humor ou comportamento observado.\n"
            "Exemplo: Tranquila e comunicativa durante a manhã."
        )
    elif chave == "sintoma":
        instrucoes = (
            "Descreva o sintoma ou intercorrência observada."
        )
    else:
        instrucoes = "Digite sua observação."

    await query.message.reply_text(
        f"Registro: {tipo}\n\n"
        f"{instrucoes}\n\n"
        "Envie /cancelar para cancelar."
    )

    return AGUARDANDO_VALOR


async def salvar_registro(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    if not update.effective_user or not update.message:
        return ConversationHandler.END

    valor = update.message.text.strip()

    if valor.lower() == "/cancelar":
        await update.message.reply_text(
            "Registro cancelado.",
            reply_markup=teclado_principal(),
        )
        return ConversationHandler.END

    chave = context.user_data.get("chave_registro")
    tipo = context.user_data.get("tipo_registro")

    if not chave or not tipo:
        await update.message.reply_text(
            "Não consegui identificar o tipo de registro. "
            "Comece novamente pelo menu."
        )
        return ConversationHandler.END

    if chave == "dor":
        try:
            intensidade = int(valor)

            if intensidade < 0 or intensidade > 10:
                raise ValueError

        except ValueError:
            await update.message.reply_text(
                "Informe a dor com um número inteiro entre 0 e 10.\n"
                "Exemplo: 5"
            )
            return AGUARDANDO_VALOR

    user_id = update.effective_user.id
    codigo = obter_codigo_atual(user_id)

    if not codigo:
        await update.message.reply_text(
            "Sua sessão não está vinculada a nenhum idoso. "
            "Use /entrar CODIGO novamente."
        )
        return ConversationHandler.END

    nome_usuario = obter_usuario_nome(update)

    try:
        supabase.table("registros").insert(
            {
                "codigo_idoso": codigo,
                "tipo": tipo,
                "valor": valor,
                "user_id": user_id,
                "user_name": nome_usuario,
            }
        ).execute()

        await update.message.reply_text(
            f"Registro salvo com sucesso.\n\n"
            f"Tipo: {tipo}\n"
            f"Informação: {valor}",
            reply_markup=teclado_principal(),
        )

    except Exception:
        logger.exception("Erro ao salvar registro")

        await update.message.reply_text(
            "Não foi possível salvar o registro. "
            "Tente novamente em alguns instantes."
        )

    context.user_data.pop("tipo_registro", None)
    context.user_data.pop("chave_registro", None)

    return ConversationHandler.END


async def cancelar_registro(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    context.user_data.pop("tipo_registro", None)
    context.user_data.pop("chave_registro", None)

    codigo = None
    if update.effective_user:
        codigo = obter_codigo_atual(update.effective_user.id)

    if codigo:
        await update.message.reply_text(
            "Operação cancelada.",
            reply_markup=teclado_principal(),
        )
    else:
        await update.message.reply_text("Operação cancelada.")

    return ConversationHandler.END

# ============================================================
# Cadastro de novo idoso
# ============================================================

# Palavras que não servem para formar o código (ex.: "Dona Maria" -> MARIA)
TITULOS_IGNORADOS = {"DONA", "SEU", "SR", "SRA", "DR", "DRA", "VOVO", "VOVÓ"}


def gerar_codigo_base(nome: str) -> str:
    """
    Gera a parte de letras do código a partir do nome do idoso.
    Remove acentos, ignora títulos e limita a 8 letras.
    """
    sem_acentos = (
        unicodedata.normalize("NFKD", nome)
        .encode("ascii", "ignore")
        .decode("ascii")
    )

    for palavra in sem_acentos.split():
        letras = re.sub(r"[^A-Za-z]", "", palavra).upper()

        if letras and letras not in TITULOS_IGNORADOS:
            return letras[:8]

    return "IDOSO"


def criar_idoso(nome: str) -> Optional[str]:
    """
    Cria o idoso no banco com um código único e retorna esse código.
    Retorna None se não conseguir gerar um código livre.
    """
    base = gerar_codigo_base(nome)

    for tentativa in range(20):
        # As primeiras tentativas usam 2 dígitos; depois, 4 dígitos.
        if tentativa < 10:
            sufixo = random.randint(10, 99)
        else:
            sufixo = random.randint(1000, 9999)

        codigo = f"{base}{sufixo}"

        existente = buscar_primeiro(
            supabase.table("idosos").select("codigo").eq("codigo", codigo)
        )

        if existente:
            continue

        try:
            supabase.table("idosos").insert(
                {"codigo": codigo, "nome": nome}
            ).execute()
            return codigo
        except Exception:
            # Pode ter acontecido de outro usuário criar o mesmo código
            # ao mesmo tempo. Tentamos de novo com outro número.
            logger.warning("Falha ao inserir código %s, tentando outro", codigo)

    return None


async def iniciar_cadastro(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """
    Início do cadastro. Funciona tanto pelo comando /novoidoso
    quanto pelo botão "Cadastrar novo idoso".
    """
    if update.callback_query:
        await update.callback_query.answer()
        mensagem = update.callback_query.message
    else:
        mensagem = update.message

    # Garante que nenhum registro anterior fique pendente
    context.user_data.pop("tipo_registro", None)
    context.user_data.pop("chave_registro", None)

    await mensagem.reply_text(
        "Vamos cadastrar um novo idoso.\n\n"
        "Digite o nome da pessoa idosa.\n"
        "Exemplo: Dona Maria\n\n"
        "Envie /cancelar para cancelar."
    )

    return AGUARDANDO_NOME


async def receber_nome_idoso(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """
    Recebe o nome, cria o idoso, vincula o usuário e mostra o código.
    """
    if not update.effective_user or not update.message:
        return ConversationHandler.END

    # Remove espaços extras no começo, no fim e no meio do nome
    nome = " ".join(update.message.text.split())

    if len(nome) < 2 or len(nome) > 60:
        await update.message.reply_text(
            "O nome precisa ter entre 2 e 60 caracteres. "
            "Digite novamente ou envie /cancelar."
        )
        return AGUARDANDO_NOME

    user_id = update.effective_user.id
    nome_usuario = obter_usuario_nome(update)

    try:
        codigo = criar_idoso(nome)

        if not codigo:
            await update.message.reply_text(
                "Não consegui gerar um código para este idoso agora. "
                "Tente novamente em instantes."
            )
            return ConversationHandler.END

        # Vincula quem cadastrou ao novo idoso
        supabase.table("vinculos_cuidadores").upsert(
            {
                "user_id": user_id,
                "user_name": nome_usuario,
                "codigo_idoso": codigo,
            },
            on_conflict="user_id,codigo_idoso",
        ).execute()

        # Já deixa esse idoso como o atual do usuário
        supabase.table("sessoes_ativas").upsert(
            {
                "user_id": user_id,
                "codigo_idoso": codigo,
            },
            on_conflict="user_id",
        ).execute()

        await update.message.reply_text(
            f"Idoso cadastrado com sucesso!\n\n"
            f"Nome: {nome}\n"
            f"Código: {codigo}\n\n"
            f"Para que outros cuidadores participem, peça que enviem:\n"
            f"/entrar {codigo}\n\n"
            "Guarde esse código e compartilhe apenas com pessoas "
            "autorizadas.",
            reply_markup=teclado_principal(),
        )

    except Exception:
        logger.exception("Erro ao cadastrar idoso")

        await update.message.reply_text(
            "Ocorreu um erro ao cadastrar o idoso. "
            "Tente novamente em alguns instantes."
        )

    return ConversationHandler.END
# ============================================================
# Consultas
# ============================================================

def obter_intervalo_dia_atual():
    agora = datetime.now(FUSO_HORARIO)

    inicio = agora.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )

    fim = inicio + timedelta(days=1)

    return inicio, fim


def buscar_registros_periodo(
    codigo: str,
    inicio: datetime,
    fim: datetime,
) -> list[dict]:
    resposta = (
        supabase
        .table("registros")
        .select("*")
        .eq("codigo_idoso", codigo)
        .gte("created_at", inicio.isoformat())
        .lt("created_at", fim.isoformat())
        .order("created_at", desc=False)
        .execute()
    )

    return resposta.data or []


async def mostrar_registros_hoje(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not update.effective_user:
        return

    codigo = obter_codigo_atual(update.effective_user.id)

    if not codigo:
        mensagem = (
            "Você não está conectado a nenhum idoso. "
            "Use /entrar CODIGO antes de consultar registros."
        )

        if update.callback_query:
            await update.callback_query.message.reply_text(mensagem)
        else:
            await update.message.reply_text(mensagem)

        return

    inicio, fim = obter_intervalo_dia_atual()

    try:
        registros = buscar_registros_periodo(codigo, inicio, fim)

        if not registros:
            texto = (
                f"Não há registros para hoje no idoso {codigo}."
            )
        else:
            linhas = [
                f"Registros de hoje — idoso {codigo}",
                "",
            ]

            for registro in registros:
                horario = formatar_data(registro["created_at"])
                tipo = registro["tipo"]
                valor = registro["valor"]
                usuario = registro.get("user_name") or "usuário não informado"

                linhas.append(
                    f"{horario} — {tipo}\n"
                    f"{valor}\n"
                    f"Registrado por: {usuario}\n"
                )

            texto = "\n".join(linhas)

        if update.callback_query:
            await update.callback_query.message.reply_text(
                texto,
                reply_markup=teclado_voltar(),
            )
        else:
            await update.message.reply_text(
                texto,
                reply_markup=teclado_voltar(),
            )

    except Exception:
        logger.exception("Erro ao consultar registros de hoje")

        mensagem = (
            "Não foi possível consultar os registros agora."
        )

        if update.callback_query:
            await update.callback_query.message.reply_text(mensagem)
        else:
            await update.message.reply_text(mensagem)


async def comando_hoje(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    await mostrar_registros_hoje(update, context)


async def gerar_resumo(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    await query.answer()

    if not update.effective_user:
        return

    codigo = obter_codigo_atual(update.effective_user.id)

    if not codigo:
        await query.message.reply_text(
            "Você não está conectado a nenhum idoso. "
            "Use /entrar CODIGO antes de consultar registros."
        )
        return

    try:
        dias = int(query.data.split(":", 1)[1])
    except ValueError:
        await query.message.reply_text(
            "Período de resumo inválido."
        )
        return

    agora = datetime.now(FUSO_HORARIO)

    fim = agora
    inicio = agora - timedelta(days=dias)

    try:
        registros = buscar_registros_periodo(codigo, inicio, fim)

        if not registros:
            await query.message.reply_text(
                f"Não há registros nos últimos {dias} dias "
                f"para o idoso {codigo}.",
                reply_markup=teclado_voltar(),
            )
            return

        agrupados = defaultdict(list)

        for registro in registros:
            agrupados[registro["tipo"]].append(registro)

        linhas = [
            f"Resumo dos últimos {dias} dias",
            f"Idoso: {codigo}",
            "",
        ]

        for tipo in sorted(agrupados.keys()):
            linhas.append(f"=== {tipo} ===")

            for registro in agrupados[tipo]:
                data = formatar_data(registro["created_at"])
                valor = registro["valor"]
                usuario = registro.get("user_name") or "não informado"

                linhas.append(
                    f"{data} — {valor} "
                    f"(por {usuario})"
                )

            linhas.append("")

        texto = "\n".join(linhas)

        for parte in quebrar_mensagem(texto):
            await query.message.reply_text(
                parte,
                reply_markup=teclado_voltar(),
            )

    except Exception:
        logger.exception("Erro ao gerar resumo")

        await query.message.reply_text(
            "Não foi possível gerar o resumo agora. "
            "Tente novamente em alguns instantes."
        )


# ============================================================
# Callbacks gerais
# ============================================================

async def voltar_menu(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    await query.answer()

    if not update.effective_user:
        return

    codigo = obter_codigo_atual(update.effective_user.id)

    if not codigo:
        await query.message.reply_text(
            "Você não está conectado a nenhum idoso. "
            "Use /entrar CODIGO."
        )
        return

    await enviar_menu(update, codigo)


async def sair_por_botao(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    await query.answer()

    if not update.effective_user:
        return

    user_id = update.effective_user.id

    try:
        supabase.table("sessoes_ativas").delete().eq(
            "user_id", user_id
        ).execute()

        await query.message.reply_text(
            "Você saiu do cuidado atual. "
            "Os registros existentes foram mantidos."
        )

    except Exception:
        logger.exception("Erro ao sair pelo botão")

        await query.message.reply_text(
            "Não foi possível sair agora. Tente novamente."
        )


# ============================================================
# Erros
# ============================================================

async def tratar_erro(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    logger.error(
        "Erro não tratado durante o processamento de uma atualização",
        exc_info=context.error,
    )

    try:
        if isinstance(update, Update) and update.effective_message:
            await update.effective_message.reply_text(
                "Ocorreu um erro inesperado. "
                "Tente novamente em alguns instantes."
            )
    except Exception:
        logger.exception("Não foi possível enviar mensagem de erro")


# ============================================================
# Inicialização da aplicação
# ============================================================

def criar_aplicacao() -> Application:
    application = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .build()
    )

    conversation_registro = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                iniciar_registro,
                pattern=r"^registro:",
            ),
            CommandHandler("novoidoso", iniciar_cadastro),
            CallbackQueryHandler(
                iniciar_cadastro,
                pattern=r"^acao:novoidoso$",
            ),
        ],
        states={
            AGUARDANDO_VALOR: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    salvar_registro,
                ),
            ],
            AGUARDANDO_NOME: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    receber_nome_idoso,
                ),
            ],
        },
        fallbacks=[
            CommandHandler("cancelar", cancelar_registro),
        ],
        allow_reentry=True,
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("entrar", entrar))
    application.add_handler(CommandHandler("sair", sair))
    application.add_handler(CommandHandler("hoje", comando_hoje))
    application.add_handler(CommandHandler("meusidosos", meus_idosos))

    application.add_handler(conversation_registro)

    application.add_handler(
        CallbackQueryHandler(
            mostrar_registros_hoje,
            pattern=r"^ver:hoje$",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            gerar_resumo,
            pattern=r"^resumo:(7|14)$",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            voltar_menu,
            pattern=r"^acao:menu$",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            sair_por_botao,
            pattern=r"^acao:sair$",
        )
    )

    application.add_error_handler(tratar_erro)

    return application


def main() -> None:
    logger.info("Iniciando bot Cuidar+")

    # O Python 3.14 não cria mais um event loop automaticamente,
    # então criamos um antes de iniciar o polling.
    asyncio.set_event_loop(asyncio.new_event_loop())

    application = criar_aplicacao()

    # O polling mantém o bot conectado ao Telegram.
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
    )


if __name__ == "__main__":
    main()