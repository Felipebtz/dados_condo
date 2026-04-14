from __future__ import annotations

import base64
from pathlib import Path
from typing import Dict, List, Tuple
import itertools
import json
import re
import unicodedata

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


st.set_page_config(
    page_title="Condo Center - Inteligencia de Consumo",
    page_icon="📊",
    layout="wide",
)


# Ordem de exibicao dos dias da semana no Brasil.
DIAS_ORDENADOS = [
    "Segunda-feira",
    "Terca-feira",
    "Quarta-feira",
    "Quinta-feira",
    "Sexta-feira",
    "Sabado",
    "Domingo",
]


MAPA_DIA_SEMANA = {
    "segunda": "Segunda-feira",
    "segunda_feira": "Segunda-feira",
    "segunda-feira": "Segunda-feira",
    "monday": "Segunda-feira",
    "seg": "Segunda-feira",
    "terca": "Terca-feira",
    "terca_feira": "Terca-feira",
    "terca-feira": "Terca-feira",
    "tuesday": "Terca-feira",
    "ter": "Terca-feira",
    "quarta": "Quarta-feira",
    "quarta_feira": "Quarta-feira",
    "quarta-feira": "Quarta-feira",
    "wednesday": "Quarta-feira",
    "qua": "Quarta-feira",
    "quinta": "Quinta-feira",
    "quinta_feira": "Quinta-feira",
    "quinta-feira": "Quinta-feira",
    "thursday": "Quinta-feira",
    "qui": "Quinta-feira",
    "sexta": "Sexta-feira",
    "sexta_feira": "Sexta-feira",
    "sexta-feira": "Sexta-feira",
    "friday": "Sexta-feira",
    "sex": "Sexta-feira",
    "sabado": "Sabado",
    "saturday": "Sabado",
    "sab": "Sabado",
    "domingo": "Domingo",
    "sunday": "Domingo",
    "dom": "Domingo",
}


def format_brl(value: float) -> str:
    """Formata valores numericos no padrao monetario brasileiro."""
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def style_plotly_figure(fig: go.Figure, *, height: int = 360) -> go.Figure:
    """Padroniza layout dos graficos para um visual mais legivel."""
    fig.update_layout(
        template="plotly_white",
        height=height,
        margin=dict(l=16, r=16, t=56, b=16),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#ffffff",
        font=dict(family="Inter, Segoe UI, sans-serif", size=13, color="#1e293b"),
        title_font=dict(size=18, color="#0f172a"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    fig.update_xaxes(
        title_font=dict(color="#1e293b"),
        tickfont=dict(color="#334155"),
        gridcolor="#e2e8f0",
        zerolinecolor="#cbd5e1",
    )
    fig.update_yaxes(
        title_font=dict(color="#1e293b"),
        tickfont=dict(color="#334155"),
        gridcolor="#e2e8f0",
        zerolinecolor="#cbd5e1",
    )
    return fig


def find_shelf_report_file() -> Path | None:
    """Localiza o PDF do relatorio Shelf-PDV no diretorio do app."""
    base_path = Path(__file__).parent
    for pdf_path in sorted(base_path.glob("*.pdf")):
        normalized_name = normalize_text(pdf_path.stem)
        if "relatorio" in normalized_name and "shelf" in normalized_name and "pdv" in normalized_name:
            return pdf_path
    return None


@st.cache_data(show_spinner=False)
def load_binary_file(file_path: str) -> bytes:
    """Carrega arquivo binario com cache para evitar releitura."""
    return Path(file_path).read_bytes()


def normalize_text(value: str) -> str:
    """Normaliza texto para facilitar match de colunas."""
    if value is None:
        return ""
    value = str(value).strip().lower()
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^a-z0-9]+", "_", value).strip("_")
    return value


def parse_numeric_value(value: object) -> float | None:
    """Converte texto numerico em float, suportando pt-BR e padrao internacional."""
    if pd.isna(value):
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    if not text:
        return None

    text = re.sub(r"[^\d,.\-]", "", text)
    if not text:
        return None

    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        parts = text.split(",")
        text = text.replace(".", "").replace(",", ".") if len(parts[-1]) <= 2 else text.replace(",", "")
    elif "." in text:
        parts = text.split(".")
        text = text if len(parts[-1]) <= 2 else text.replace(".", "")

    try:
        return float(text)
    except ValueError:
        return None


def parse_brl_number(series: pd.Series) -> pd.Series:
    """Converte numeros em formato misto (pt-BR/internacional) para float."""
    return pd.to_numeric(series.apply(parse_numeric_value), errors="coerce")


def parse_hour_value(value: object) -> int | None:
    """Extrai hora inteira de formatos como '19', '19:30' ou '19h'."""
    if pd.isna(value):
        return None
    if isinstance(value, (int, float)):
        hour = int(value)
        return hour if 0 <= hour <= 23 else None

    text = str(value).strip()
    if not text:
        return None

    match = re.search(r"\b([01]?\d|2[0-3])\b", text)
    if not match:
        return None
    return int(match.group(1))


def normalize_weekday_label(value: object) -> str:
    """Padroniza nome do dia da semana para exibicao consistente."""
    key = normalize_text(value)
    return MAPA_DIA_SEMANA.get(key, "Nao informado")


def infer_categoria(produto: str) -> str:
    """Cria categorias simples caso a fonte nao traga categoria pronta."""
    if not isinstance(produto, str) or not produto.strip():
        return "Outros"
    p = normalize_text(produto)
    regras = {
        "Bebidas": ["agua", "refrigerante", "coca", "suco", "energetico", "cerveja", "isotonico", "cha"],
        "Snacks e Doces": ["chocolate", "biscoito", "salgadinho", "batata", "kit_kat", "trident", "bombom"],
        "Mercearia": ["arroz", "feijao", "leite", "manteiga", "molho", "oleo", "pao", "macarrao", "miojo"],
        "Higiene e Limpeza": ["sabonete", "papel_higienico", "absorvente", "lavadora", "secadora"],
    }
    for categoria, termos in regras.items():
        if any(t in p for t in termos):
            return categoria
    return "Outros"


@st.cache_data(show_spinner=False)
def load_data() -> pd.DataFrame:
    """
    Carrega dados de transacao em ordem de prioridade:
    1) Excel
    2) JSON
    3) JSON label (Looker export)
    """
    base_path = Path(__file__).parent
    candidates = [
        base_path / "Transações Geral.xlsx",
        base_path / "Transações Geral.json",
        base_path / "Transações Geral.json_label",
    ]

    erros: List[str] = []

    for file_path in candidates:
        if not file_path.exists():
            continue
        try:
            if file_path.suffix.lower() == ".xlsx":
                df = pd.read_excel(file_path)
            else:
                # O JSON do Looker costuma vir em lista de objetos.
                with file_path.open("r", encoding="utf-8") as f:
                    raw = json.load(f)
                if isinstance(raw, dict):
                    # Fallback para estrutura {"data": [...]}.
                    raw = raw.get("data", [])
                df = pd.DataFrame(raw)

            if not df.empty:
                df["__source_file__"] = file_path.name
                return df
        except Exception as exc:  # pragma: no cover - robustez para arquivos de usuario
            erros.append(f"{file_path.name}: {exc}")

    msg = (
        "Nenhum arquivo de dados valido foi encontrado. "
        "Inclua pelo menos um dos arquivos: "
        "`Transações Geral.xlsx`, `Transações Geral.json` ou `Transações Geral.json_label`."
    )
    if erros:
        msg += "\n\nErros encontrados:\n- " + "\n- ".join(erros)
    raise FileNotFoundError(msg)


def transform_data(df: pd.DataFrame) -> pd.DataFrame:
    """Padroniza schema e cria colunas derivadas para analise."""
    if df.empty:
        return df

    normalized_cols = {c: normalize_text(c) for c in df.columns}
    df = df.rename(columns=normalized_cols).copy()

    # Mapeamento flexivel dos nomes do Looker para schema analitico.
    coluna_map = {
        "data_transacao": ["data_transacao", "data_de_compra", "data"],
        "hora_transacao": ["hora_transacao", "hora"],
        "dia_semana": ["dia_semana"],
        "id_usuario": ["id_usuario", "cliente", "usuario", "user_id"],
        "sexo": ["sexo", "genero"],
        "faixa_etaria": ["faixa_etaria", "idade_faixa"],
        "produto": ["produto", "nome_produto"],
        "categoria_produto": ["categoria_produto", "categoria", "departamento"],
        "valor_transacao": ["valor_transacao", "preco_total", "preco_pago", "valor"],
        "condominio": ["condominio", "pdv", "local", "unidade"],
        "id_transacao": ["id_transacao", "transacao_id", "id_pedido", "pedido_id"],
    }

    out = pd.DataFrame()
    for destino, opcoes in coluna_map.items():
        origem = next((c for c in opcoes if c in df.columns), None)
        out[destino] = df[origem] if origem else pd.NA

    if "canal" in df.columns:
        out["canal"] = df["canal"]
    else:
        out["canal"] = "Nao informado"

    if "__source_file__" in df.columns:
        out["source_file"] = df["__source_file__"]

    # Conversoes de tipo.
    out["data_transacao"] = pd.to_datetime(out["data_transacao"], errors="coerce", dayfirst=True)
    out["valor_transacao"] = parse_brl_number(out["valor_transacao"])
    out["id_usuario"] = out["id_usuario"].fillna("Consumidor nao informado").astype(str).str.strip()
    out["produto"] = out["produto"].fillna("Produto nao informado").astype(str).str.strip()
    out["condominio"] = out["condominio"].fillna("Condominio nao informado").astype(str).str.strip()
    out["sexo"] = out["sexo"].fillna("Nao informado").astype(str).str.strip()
    out["faixa_etaria"] = out["faixa_etaria"].fillna("Nao informado").astype(str).str.strip()
    out["id_transacao"] = out["id_transacao"].fillna("").astype(str).str.strip()

    # Quando nao houver id de transacao, gera um id aproximado por usuario + minuto.
    mask_missing_id = out["id_transacao"].eq("") | out["id_transacao"].eq("nan")
    out.loc[mask_missing_id, "id_transacao"] = (
        "tx_"
        + out.loc[mask_missing_id, "id_usuario"].astype(str)
        + "_"
        + out.loc[mask_missing_id, "data_transacao"].dt.strftime("%Y%m%d%H%M").fillna("sem_data")
    )

    # Derivacoes de tempo.
    hora_coluna = out["hora_transacao"].apply(parse_hour_value) if "hora_transacao" in out.columns else pd.Series(index=out.index, dtype="float64")
    out["hora"] = out["data_transacao"].dt.hour.fillna(hora_coluna)
    out["hora"] = out["hora"].fillna(0).astype(int)
    out["data_dia"] = out["data_transacao"].dt.date
    out["ano_mes"] = out["data_transacao"].dt.to_period("M").astype(str)
    dia_por_data = out["data_transacao"].dt.dayofweek.map(
        {
            0: "Segunda-feira",
            1: "Terca-feira",
            2: "Quarta-feira",
            3: "Quinta-feira",
            4: "Sexta-feira",
            5: "Sabado",
            6: "Domingo",
        }
    )

    if out["dia_semana"].isna().all():
        out["dia_semana"] = dia_por_data
    else:
        out["dia_semana"] = out["dia_semana"].apply(normalize_weekday_label)
        dia_nao_info = out["dia_semana"].eq("Nao informado")
        out.loc[dia_nao_info, "dia_semana"] = dia_por_data[dia_nao_info]
        out["dia_semana"] = out["dia_semana"].fillna("Nao informado")

    # Categoria inferida se necessario.
    missing_categoria = out["categoria_produto"].isna() | out["categoria_produto"].astype(str).str.strip().eq("")
    out.loc[missing_categoria, "categoria_produto"] = out.loc[missing_categoria, "produto"].map(infer_categoria)
    out["categoria_produto"] = out["categoria_produto"].fillna("Outros").astype(str).str.strip()

    out = out.dropna(subset=["data_transacao", "valor_transacao"])
    return out


def build_filters(df: pd.DataFrame) -> pd.DataFrame:
    """Cria filtros globais da landing page."""
    st.subheader("Filtros globais")
    min_date = df["data_transacao"].min().date()
    max_date = df["data_transacao"].max().date()

    f1, f2, f3, f4 = st.columns(4)
    with f1:
        period = st.date_input("Periodo", value=(min_date, max_date), min_value=min_date, max_value=max_date)
    with f2:
        condominios = st.multiselect(
            "Condominio",
            options=sorted(df["condominio"].dropna().unique().tolist()),
            default=[],
            placeholder="Todos",
        )
    with f3:
        faixas = st.multiselect(
            "Faixa etaria",
            options=sorted(df["faixa_etaria"].dropna().unique().tolist()),
            default=[],
            placeholder="Todas",
        )
    with f4:
        sexos = st.multiselect(
            "Sexo",
            options=sorted(df["sexo"].dropna().unique().tolist()),
            default=[],
            placeholder="Todos",
        )

    if isinstance(period, tuple) and len(period) == 2:
        start_date, end_date = period
    else:
        start_date, end_date = min_date, max_date

    filtered = df[
        (df["data_transacao"].dt.date >= start_date)
        & (df["data_transacao"].dt.date <= end_date)
    ].copy()

    if condominios:
        filtered = filtered[filtered["condominio"].isin(condominios)]
    if faixas:
        filtered = filtered[filtered["faixa_etaria"].isin(faixas)]
    if sexos:
        filtered = filtered[filtered["sexo"].isin(sexos)]

    return filtered


def build_kpis(df: pd.DataFrame) -> None:
    """Renderiza cards de metricas principais."""
    total_transacoes = int(df["id_transacao"].nunique())
    total_faturado = float(df["valor_transacao"].sum())
    usuarios_unicos = int(df["id_usuario"].nunique())
    condominios_unicos = int(df["condominio"].nunique())

    ticket_usuario = total_faturado / usuarios_unicos if usuarios_unicos else 0.0
    ticket_condominio = total_faturado / condominios_unicos if condominios_unicos else 0.0

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total de transacoes", f"{total_transacoes:,}".replace(",", "."))
    c2.metric("Total faturado", format_brl(total_faturado))
    c3.metric("Ticket medio por usuario", format_brl(ticket_usuario))
    c4.metric("Usuarios unicos", f"{usuarios_unicos:,}".replace(",", "."))
    c5.metric("Ticket medio por condominio", format_brl(ticket_condominio))


def compute_cooccurrence(df: pd.DataFrame, top_n: int = 15) -> pd.DataFrame:
    """Calcula pares de produtos comprados juntos por transacao."""
    basket = (
        df.groupby("id_transacao")["produto"]
        .apply(lambda x: sorted(set(p for p in x if isinstance(p, str) and p.strip())))
    )
    pair_counts: Dict[Tuple[str, str], int] = {}
    for products in basket:
        if len(products) < 2:
            continue
        for pair in itertools.combinations(products, 2):
            pair_counts[pair] = pair_counts.get(pair, 0) + 1

    if not pair_counts:
        return pd.DataFrame(columns=["produto_a", "produto_b", "frequencia"])

    out = (
        pd.DataFrame(
            [{"produto_a": a, "produto_b": b, "frequencia": c} for (a, b), c in pair_counts.items()]
        )
        .sort_values("frequencia", ascending=False)
        .head(top_n)
    )
    return out


def compute_cross_sell_matrix(df: pd.DataFrame, top_products: int = 15) -> pd.DataFrame:
    """Matriz de correlacao simples entre produtos por transacao."""
    base = df["produto"].value_counts().head(top_products).index.tolist()
    if len(base) < 2:
        return pd.DataFrame()

    basket = (
        df[df["produto"].isin(base)]
        .assign(presenca=1)
        .pivot_table(index="id_transacao", columns="produto", values="presenca", fill_value=0)
    )
    if basket.shape[1] < 2:
        return pd.DataFrame()
    corr = basket.corr().round(2)
    return corr


def build_charts(df: pd.DataFrame) -> None:
    """Renderiza principais visualizacoes da landing page."""
    c1, c2 = st.columns(2)

    # Consumo por dia da semana.
    consumo_dia = df.groupby("dia_semana", as_index=False)["valor_transacao"].sum()
    consumo_dia["dia_semana"] = pd.Categorical(consumo_dia["dia_semana"], categories=DIAS_ORDENADOS, ordered=True)
    consumo_dia = consumo_dia.sort_values("dia_semana")
    fig_dia = px.bar(
        consumo_dia,
        x="dia_semana",
        y="valor_transacao",
        title="Consumo por dia da semana",
        color="valor_transacao",
        color_continuous_scale="Purples",
        labels={"valor_transacao": "Faturamento (R$)", "dia_semana": "Dia"},
    )
    fig_dia.update_xaxes(tickangle=-20)
    style_plotly_figure(fig_dia, height=380)
    c1.plotly_chart(fig_dia, width="stretch")

    # Heatmap de horario x dia.
    heat = (
        df.pivot_table(index="dia_semana", columns="hora", values="valor_transacao", aggfunc="sum", fill_value=0)
        .reindex(DIAS_ORDENADOS)
    )
    fig_heat = go.Figure(
        data=go.Heatmap(
            z=heat.values,
            x=heat.columns.tolist(),
            y=heat.index.tolist(),
            colorscale="Blues",
            colorbar={"title": "R$"},
        )
    )
    fig_heat.update_layout(title="Horarios de pico (dia x hora)", xaxis_title="Hora", yaxis_title="Dia da semana")
    style_plotly_figure(fig_heat, height=380)
    c2.plotly_chart(fig_heat, width="stretch")

    c3, c4 = st.columns(2)
    sexo_valor = df.groupby("sexo", as_index=False)["valor_transacao"].sum().sort_values("valor_transacao", ascending=False)
    fig_sexo = px.pie(sexo_valor, names="sexo", values="valor_transacao", title="Consumo por sexo", hole=0.5, color_discrete_sequence=px.colors.sequential.Purples)
    style_plotly_figure(fig_sexo, height=360)
    c3.plotly_chart(fig_sexo, width="stretch")

    faixa_valor = df.groupby("faixa_etaria", as_index=False)["valor_transacao"].sum().sort_values("valor_transacao", ascending=False).head(10)
    fig_faixa = px.bar(
        faixa_valor,
        x="faixa_etaria",
        y="valor_transacao",
        title="Consumo por faixa etaria",
        color="valor_transacao",
        color_continuous_scale="Blues",
        labels={"valor_transacao": "Faturamento (R$)", "faixa_etaria": "Faixa etaria"},
    )
    fig_faixa.update_xaxes(tickangle=-20)
    style_plotly_figure(fig_faixa, height=360)
    c4.plotly_chart(fig_faixa, width="stretch")

    c5, c6 = st.columns(2)
    top_prod = df.groupby("produto", as_index=False)["valor_transacao"].sum().sort_values("valor_transacao", ascending=False).head(12)
    fig_prod = px.bar(
        top_prod,
        x="valor_transacao",
        y="produto",
        orientation="h",
        title="Top produtos",
        color="valor_transacao",
        color_continuous_scale="Purples",
        labels={"valor_transacao": "Faturamento (R$)", "produto": "Produto"},
    )
    style_plotly_figure(fig_prod, height=420)
    c5.plotly_chart(fig_prod, width="stretch")

    top_cat = df.groupby("categoria_produto", as_index=False)["valor_transacao"].sum().sort_values("valor_transacao", ascending=False).head(10)
    fig_cat = px.bar(
        top_cat,
        x="categoria_produto",
        y="valor_transacao",
        title="Top categorias",
        color="valor_transacao",
        color_continuous_scale="Blues",
        labels={"valor_transacao": "Faturamento (R$)", "categoria_produto": "Categoria"},
    )
    fig_cat.update_xaxes(tickangle=-20)
    style_plotly_figure(fig_cat, height=420)
    c6.plotly_chart(fig_cat, width="stretch")


def build_insights(df: pd.DataFrame) -> None:
    """Gera insights automaticos em linguagem de negocio."""
    st.subheader("Insights acionaveis")

    if df.empty:
        st.info("Nao ha dados para gerar insights com os filtros atuais.")
        return

    top_produto = df.groupby("produto")["valor_transacao"].sum().idxmax()
    melhor_publico = (
        df.groupby(["produto", "sexo", "faixa_etaria", "condominio"], as_index=False)["valor_transacao"]
        .sum()
        .sort_values("valor_transacao", ascending=False)
        .head(1)
    )
    melhor_linha = melhor_publico.iloc[0]

    pico_hora = df.groupby("hora")["valor_transacao"].sum().idxmax()
    top_dias = (
        df.groupby("dia_semana")["valor_transacao"]
        .sum()
        .reindex(DIAS_ORDENADOS)
        .sort_values(ascending=False)
        .head(2)
        .index.tolist()
    )

    cooc = compute_cooccurrence(df, top_n=1)
    combo_texto = "Sem combinacoes relevantes."
    if not cooc.empty:
        row = cooc.iloc[0]
        combo_texto = f"{row['produto_a']} + {row['produto_b']} (aparecem juntos em {int(row['frequencia'])} transacoes)."

    st.markdown(
        f"""
        - **Produto com melhor performance por publico:** `{melhor_linha['produto']}` se destaca em `{melhor_linha['condominio']}` para o publico `{melhor_linha['sexo']}` / `{melhor_linha['faixa_etaria']}`.
        - **Janela ideal de ativacao:** maior consumo as `{int(pico_hora):02d}h`, com maior concentracao em `{", ".join(top_dias)}`.
        - **Cross-sell natural mais forte:** {combo_texto}
        - **Foco comercial imediato:** escalar campanhas do produto `{top_produto}` nos condominios com maior densidade de consumo no horario de pico.
        """
    )


def apply_visual_theme() -> None:
    """Aplica um visual em tons roxo/azul para landing page."""
    st.markdown(
        """
        <style>
        .block-container {
            max-width: 1300px;
            padding-top: 1.2rem;
            padding-bottom: 2rem;
        }
        .stApp {
            background: #f8fafc;
            color: #0f172a;
        }
        .stApp h1, .stApp h2, .stApp h3, .stApp h4 {
            color: #0f172a !important;
        }
        .stApp p, .stApp li, .stApp label, .stApp span {
            color: #1e293b;
        }
        [data-testid="stMarkdownContainer"] p,
        [data-testid="stMarkdownContainer"] li {
            color: #0f172a !important;
        }
        [data-testid="stMarkdownContainer"] code {
            color: #22c55e !important;
            background: #0b1222;
            border: 1px solid #1f2937;
            border-radius: 8px;
            padding: 0.1rem 0.35rem;
        }
        [data-testid="stHeadingWithActionElements"] h1,
        [data-testid="stHeadingWithActionElements"] h2,
        [data-testid="stHeadingWithActionElements"] h3 {
            color: #0f172a !important;
        }
        [data-testid="stMetric"] {
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 12px;
            padding: 0.9rem 1rem;
            box-shadow: 0 2px 8px rgba(15, 23, 42, 0.05);
        }
        [data-testid="stMetricLabel"] {
            color: #334155;
            font-weight: 600;
        }
        [data-testid="stMetricValue"] {
            color: #0f172a;
        }
        .stPlotlyChart, [data-testid="stDataFrame"] {
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 12px;
            padding: 0.35rem;
            box-shadow: 0 2px 8px rgba(15, 23, 42, 0.05);
        }
        .hero-card {
            padding: 1.2rem 1.4rem;
            border-radius: 12px;
            background: #ffffff;
            border: 1px solid #e2e8f0;
            color: #0f172a;
            box-shadow: 0 2px 8px rgba(15, 23, 42, 0.05);
            margin-bottom: 1rem;
        }
        .hero-card h2 {
            color: #0f172a !important;
        }
        .hero-card p {
            margin: 0.25rem 0;
            color: #334155;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def build_shelf_report_section() -> None:
    """Renderiza acesso ao relatorio Shelf-PDV dentro do dashboard."""
    st.subheader("Relatorio Shelf - PDV")
    report_path = find_shelf_report_file()
    if not report_path:
        st.info("PDF do relatorio nao encontrado no diretorio do projeto.")
        return

    report_bytes = load_binary_file(str(report_path))

    c1, c2 = st.columns([3, 1])
    c1.caption(f"Arquivo localizado: {report_path.name}")
    c2.download_button(
        "Baixar PDF",
        data=report_bytes,
        file_name=report_path.name,
        mime="application/pdf",
        width="stretch",
    )

    show_report = st.toggle("Visualizar relatorio aqui", value=False)
    if show_report:
        encoded = base64.b64encode(report_bytes).decode("utf-8")
        st.markdown(
            f"""
            <iframe
                src="data:application/pdf;base64,{encoded}"
                width="100%"
                height="900"
                style="border: 1px solid #dbe2ff; border-radius: 12px;"
            ></iframe>
            """,
            unsafe_allow_html=True,
        )


def main() -> None:
    apply_visual_theme()

    st.markdown(
        """
        <div class="hero-card">
            <h2 style="margin:0;">Condo Center - Inteligencia de Consumo em Condominios</h2>
            <p>Visao objetiva do consumo para apoiar decisoes comerciais.</p>
            <p><strong>Fonte:</strong> dados transacionais por condominio, usuario e produto.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    build_shelf_report_section()

    try:
        df_raw = load_data()
        df = transform_data(df_raw)
    except Exception as exc:
        st.error(f"Erro ao carregar os dados: {exc}")
        st.stop()

    if "source_file" in df.columns and not df["source_file"].dropna().empty:
        st.caption(f"Base carregada: {df['source_file'].iloc[0]} | Registros validos: {len(df):,}".replace(",", "."))

    required_cols = ["data_transacao", "produto", "valor_transacao", "id_usuario", "condominio", "id_transacao"]
    missing_required = [c for c in required_cols if c not in df.columns]
    if missing_required:
        st.error(f"Colunas obrigatorias ausentes apos transformacao: {missing_required}")
        st.stop()

    df_filtered = build_filters(df)
    if df_filtered.empty:
        st.warning("Nenhum dado encontrado para os filtros selecionados.")
        st.stop()

    st.subheader("KPIs principais")
    build_kpis(df_filtered)

    st.subheader("Panorama de consumo")
    build_charts(df_filtered)

    st.subheader("Cesta de consumo")
    cooc_df = compute_cooccurrence(df_filtered, top_n=20)
    if cooc_df.empty:
        st.info("Sem dados suficientes para calcular produtos comprados juntos.")
    else:
        st.dataframe(cooc_df, width="stretch", hide_index=True)

    st.subheader("Cross-sell")
    corr = compute_cross_sell_matrix(df_filtered, top_products=12)
    if corr.empty:
        st.info("Sem dados suficientes para matriz de correlacao de produtos.")
    else:
        fig_corr = go.Figure(
            data=go.Heatmap(
                z=corr.values,
                x=corr.columns.tolist(),
                y=corr.index.tolist(),
                colorscale="RdBu",
                zmid=0,
                colorbar={"title": "Correlacao"},
            )
        )
        fig_corr.update_layout(title="Correlacao entre produtos (cross-sell natural)")
        style_plotly_figure(fig_corr, height=560)
        st.plotly_chart(fig_corr, width="stretch")

    build_insights(df_filtered)


if __name__ == "__main__":
    main()
