"""Interface Streamlit de exploração dos discursos parlamentares (somente leitura).

Lê a base de dados Parquet em `dados/` (ou em `DADOS_DIR`):
    streamlit run web/app.py
"""

import math
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
import data  # noqa: E402

st.set_page_config(
    page_title="Discursos Parlamentares — Câmara dos Deputados",
    layout="wide",
)


@st.cache_resource(show_spinner=False)
def carregar_catalogo():
    """Catálogo em memória (uma leitura por processo)."""
    return data.carregar_catalogo()


@st.cache_data(show_spinner=False)
def cached_legislaturas():
    return data.listar_legislaturas()


@st.cache_data(show_spinner=False)
def cached_partidos():
    return data.listar_partidos()


@st.cache_data(show_spinner=False)
def cached_periodo():
    return data.periodo_disponivel()


@st.cache_data(show_spinner=False)
def cached_detalhe(id_discurso: int):
    return data.detalhar(id_discurso)


with st.spinner("Carregando catálogo de discursos..."):
    catalogo = carregar_catalogo()

legislaturas = cached_legislaturas()
partidos = cached_partidos()
inicio, fim = cached_periodo()

rotulo_leg = dict(zip(legislaturas.idLegislatura, legislaturas.rotulo))
sigla_partido = dict(zip(partidos.idPartido, partidos.sigla))
rotulo_partido = {
    pid: f"{sigla} — {nome}"
    for pid, sigla, nome in zip(partidos.idPartido, partidos.sigla, partidos.nome)
}
tipos_disponiveis = sorted(catalogo.df["tipoDiscurso"].dropna().unique())

SEM_PARTIDO = 0  # sentinela do multiselect: converte em incluir_sem_partido

DEFAULTS = {
    "f_legs": [57],
    "f_partidos": [],
    "f_datas": (inicio, fim),
    "f_deputado": "",
    "f_tipo_on": False,
    "f_tipos": [],
    "f_tamanho": 50,
    "f_pagina": 1,
}
for chave, valor in DEFAULTS.items():
    st.session_state.setdefault(chave, valor)


def limpar_filtros():
    for chave, valor in DEFAULTS.items():
        st.session_state[chave] = valor
    st.session_state["_chave_filtros"] = None


st.title("Discursos Parlamentares — Câmara dos Deputados")
st.caption(
    "Pesquisa de TCC sobre discursos de deputados federais, 49ª–57ª "
    "legislaturas (1991–2027). Fonte: Dados Abertos da Câmara."
)

with st.sidebar:
    st.header("Filtros")

    legislaturas_sel = st.multiselect(
        "Legislaturas",
        options=legislaturas.idLegislatura.tolist(),
        format_func=lambda x: rotulo_leg.get(x, str(x)),
        key="f_legs",
        placeholder="Selecione uma ou mais legislaturas",
        select_all=False,
        filter_mode="fuzzy",
    )

    partidos_sel = st.multiselect(
        "Partidos",
        options=[SEM_PARTIDO, *partidos.idPartido.tolist()],
        format_func=lambda x: (
            "Sem partido" if x == SEM_PARTIDO else rotulo_partido.get(x, str(x))),
        key="f_partidos",
        placeholder="Selecione um ou mais partidos",
        select_all=False,
        filter_mode="fuzzy",
    )

    datas = st.date_input(
        "Intervalo de datas",
        min_value=inicio,
        max_value=fim,
        key="f_datas",
        help="Inclui o dia final.",
    )

    st.text_input(
        "Deputado (nome ou ID)",
        key="f_deputado",
        placeholder="ex.: MICHEL TEMER ou 73552",
    )

    st.checkbox("Filtrar por tipo de discurso", key="f_tipo_on")
    if st.session_state["f_tipo_on"]:
        st.multiselect(
            "Tipos de discurso",
            options=tipos_disponiveis,
            key="f_tipos",
            placeholder="Selecione um ou mais tipos",
            select_all=False,
            filter_mode="fuzzy",
        )

    st.divider()
    gerado = data.gerado_em()
    gerado_txt = f"{gerado:%d/%m/%Y}" if gerado else "data indisponível"
    faixa_leg = (
        f"{int(legislaturas.idLegislatura.min())}ª–"
        f"{int(legislaturas.idLegislatura.max())}ª"
    )
    st.caption(
        f"Dados até {gerado_txt} · {len(catalogo.df):,} discursos · {faixa_leg}"
        .replace(",", ".")
    )

if isinstance(datas, (tuple, list)) and len(datas) == 2:
    data_inicio, data_fim = datas
elif isinstance(datas, (tuple, list)) and len(datas) == 1:
    data_inicio, data_fim = datas[0], datas[0]
else:
    data_inicio, data_fim = inicio, fim

partidos_sel = [p for p in partidos_sel if p != SEM_PARTIDO]

filtros = data.Filtros(
    legislaturas=tuple(legislaturas_sel),
    partidos=tuple(partidos_sel),
    incluir_sem_partido=SEM_PARTIDO in st.session_state["f_partidos"],
    data_inicio=data_inicio,
    data_fim=data_fim,
    deputado=st.session_state["f_deputado"],
    tipos=tuple(st.session_state["f_tipos"]) if st.session_state["f_tipo_on"] else (),
)

chave_filtros = (
    filtros.legislaturas, filtros.partidos, filtros.incluir_sem_partido,
    filtros.data_inicio, filtros.data_fim, filtros.deputado.strip(),
    filtros.tipos, st.session_state["f_tamanho"],
)
if st.session_state.get("_chave_filtros") != chave_filtros:
    st.session_state["f_pagina"] = 1
    st.session_state["_chave_filtros"] = chave_filtros

chave_curta = abs(hash(chave_filtros)) % 100000


def resumo_filtros() -> str:
    partes = []
    if filtros.legislaturas:
        partes.append("Leg.: " + ", ".join(f"{x}ª" for x in sorted(filtros.legislaturas)))
    nomes_partido = [sigla_partido.get(x, str(x)) for x in filtros.partidos]
    if filtros.incluir_sem_partido:
        nomes_partido.append("Sem partido")
    if nomes_partido:
        partes.append("Partido: " + ", ".join(nomes_partido))
    if (filtros.data_inicio and filtros.data_fim
            and (filtros.data_inicio, filtros.data_fim) != (inicio, fim)):
        partes.append(
            f"{filtros.data_inicio:%d/%m/%Y}–{filtros.data_fim:%d/%m/%Y}")
    if filtros.deputado.strip():
        partes.append(f"Deputado: {filtros.deputado.strip()}")
    if filtros.tipos:
        partes.append("Tipo: " + ", ".join(filtros.tipos))
    return " · ".join(partes) if partes else "Nenhum filtro"


secao = st.radio(
    "Seção",
    ["Discursos", "Agregados", "Cobertura"],
    horizontal=True,
    label_visibility="collapsed",
)


def exibir_detalhe(id_discurso):
    discurso = cached_detalhe(id_discurso)
    if discurso is None:
        st.warning("Discurso não encontrado.")
        return
    partido = discurso.partido
    if partido is None or (isinstance(partido, float) and pd.isna(partido)):
        partido = "Sem partido"
    st.subheader(f"{discurso.deputado} — {partido}")
    st.caption(
        f"{discurso.dataHoraInicio:%d/%m/%Y %H:%M} · "
        f"{int(discurso.idLegislatura)}ª legislatura · "
        f"{discurso.tipoDiscurso or 'tipo não informado'}"
    )
    if discurso.transcricao:
        with st.expander("Transcrição (texto integral)", expanded=True):
            st.write(discurso.transcricao)
    else:
        st.info("Sem transcrição registrada para este discurso.")
    if discurso.sumario:
        st.markdown("**Sumário**")
        st.write(discurso.sumario)
    if discurso.keywords:
        st.markdown("**Palavras-chave**")
        st.write(discurso.keywords)
    if discurso.urlTexto:
        st.caption("Fonte externa (página da Câmara):")
        st.link_button("Abrir fonte na Câmara", discurso.urlTexto)


def barra_resultados(total: int, com_tamanho: bool):
    """Barra pós-pesquisa, acima dos resultados."""
    colunas = st.columns([1.1, 3.0, 1.0, 1.0], vertical_alignment="bottom")
    colunas[0].metric("Discursos", f"{total:,}".replace(",", "."))
    colunas[1].caption(f"Filtros ativos: {resumo_filtros()}")
    if com_tamanho:
        colunas[2].selectbox(
            "Itens por página", options=[25, 50, 100], key="f_tamanho")
    else:
        colunas[2].write("")
    colunas[3].button(
        "Limpar filtros", on_click=limpar_filtros, width="stretch")


def ir_para_pagina(max_pag: int):
    """Callback do campo inline: valida o número e aplica o salto."""
    bruto = st.session_state.get("f_pagina_input", "")
    try:
        alvo = int(str(bruto).strip())
    except (TypeError, ValueError):
        alvo = st.session_state["f_pagina"]
    alvo = min(max(1, alvo), max_pag)
    st.session_state["f_pagina"] = alvo
    st.session_state["f_pagina_input"] = str(alvo)


def navegacao(total: int, pagina: int, max_pag: int, offset: int, tamanho: int):
    """Paginação abaixo da tabela: uma linha centralizada de controles."""
    primeiro = min(offset + 1, total) if total else 0
    ultimo = min(offset + tamanho, total)

    # Mantém o campo sincronizado quando a página muda por Anterior/Próxima.
    if st.session_state.get("f_pagina_input") != str(pagina):
        st.session_state["f_pagina_input"] = str(pagina)

    with st.container(
        horizontal=True,
        horizontal_alignment="center",
        vertical_alignment="center",
        gap="medium",
    ):
        st.button(
            "◀ Anterior",
            disabled=pagina <= 1,
            on_click=lambda: st.session_state.update(
                f_pagina=max(1, st.session_state["f_pagina"] - 1)),
            width=240,
        )
        st.caption("Página", width="content")
        st.text_input(
            "Página",
            key="f_pagina_input",
            label_visibility="collapsed",
            on_change=ir_para_pagina,
            args=(max_pag,),
            width=64,
        )
        st.caption(
            f"de {max_pag:,} · {primeiro:,}–{ultimo:,} de {total:,}"
            .replace(",", "."),
            width="content",
        )
        st.button(
            "Próxima ▶",
            disabled=pagina >= max_pag,
            on_click=lambda: st.session_state.update(
                f_pagina=min(max_pag, st.session_state["f_pagina"] + 1)),
            width=240,
        )


if secao == "Discursos":
    total = int(data.filtrar(catalogo, filtros).size)
    barra_resultados(total, com_tamanho=True)

    if total == 0:
        st.info("Nenhum discurso encontrado com os filtros atuais.")
    else:
        tamanho = int(st.session_state["f_tamanho"])
        max_pag = max(1, math.ceil(total / tamanho))
        if st.session_state["f_pagina"] > max_pag:
            st.session_state["f_pagina"] = max_pag
        pagina = int(st.session_state["f_pagina"])
        offset = (pagina - 1) * tamanho

        posicoes = data.filtrar(catalogo, filtros)
        df = data.montar_pagina(catalogo, posicoes, offset, tamanho)

        exibicao = pd.DataFrame({
            "Data": pd.to_datetime(df.dataHoraInicio).dt.strftime("%d/%m/%Y %H:%M"),
            "Deputado": df.deputado,
            "Partido": df.partido.fillna("Sem partido"),
            "Leg.": df.idLegislatura,
            "Tipo": df.tipoDiscurso.fillna(""),
            "Sumário": df.sumario.fillna(""),
            "Fonte": df.urlTexto.fillna(""),
        })

        evento = st.dataframe(
            exibicao,
            hide_index=True,
            width="stretch",
            on_select="rerun",
            selection_mode="single-row",
            key=f"tabela_{pagina}_{chave_curta}",
            column_config={
                "Data": st.column_config.TextColumn("Data", width="small"),
                "Deputado": st.column_config.TextColumn("Deputado", width="medium"),
                "Partido": st.column_config.TextColumn("Partido", width="small"),
                "Leg.": st.column_config.NumberColumn("Leg.", width="small"),
                "Tipo": st.column_config.TextColumn("Tipo", width="medium"),
                "Sumário": st.column_config.TextColumn("Sumário", width="large"),
                "Fonte": st.column_config.LinkColumn(
                    "Fonte", display_text="fonte", width="small"),
            },
        )

        navegacao(total, pagina, max_pag, offset, tamanho)

        linhas = []
        try:
            linhas = evento.selection.rows
        except AttributeError:
            linhas = []

        indice = int(linhas[0]) if linhas else None

        st.divider()
        if indice is None:
            st.caption(
                "Selecione uma linha da tabela para ver o texto integral, "
                "o sumário e as palavras-chave."
            )
        else:
            exibir_detalhe(int(df.iloc[indice].idDiscurso))

        st.download_button(
            "Baixar esta página (CSV)",
            data=exibicao.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"discursos_pagina_{pagina}.csv",
            mime="text/csv",
        )

elif secao == "Agregados":
    total = int(data.filtrar(catalogo, filtros).size)
    barra_resultados(total, com_tamanho=False)
    dados = data.agregados(catalogo, filtros)

    if dados["partido"].empty:
        st.info("Nenhum discurso encontrado com os filtros atuais.")
    else:
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Discursos por partido")
            top = dados["partido"].head(20)
            fig = px.bar(
                top, x="discursos", y="partido", orientation="h",
                labels={"discursos": "Discursos", "partido": "Partido"},
                color="discursos", color_continuous_scale="Blues",
            )
            fig.update_layout(yaxis={"categoryorder": "total ascending"},
                              coloraxis_showscale=False, height=520)
            st.plotly_chart(fig, width="stretch")
        with col2:
            st.subheader("Deputados com mais discursos")
            fig = px.bar(
                dados["deputados"], x="discursos", y="deputado", orientation="h",
                labels={"discursos": "Discursos", "deputado": "Deputado"},
                color="discursos", color_continuous_scale="Greens",
            )
            fig.update_layout(yaxis={"categoryorder": "total ascending"},
                              coloraxis_showscale=False, height=520)
            st.plotly_chart(fig, width="stretch")

        st.subheader("Discursos por legislatura")
        fig = px.bar(
            dados["legislatura"], x="idLegislatura", y="discursos",
            labels={"idLegislatura": "Legislatura", "discursos": "Discursos"},
        )
        fig.update_xaxes(type="category")
        st.plotly_chart(fig, width="stretch")

        st.subheader("Discursos por ano")
        fig = px.line(
            dados["ano"], x="ano", y="discursos", markers=True,
            labels={"ano": "Ano", "discursos": "Discursos"},
        )
        st.plotly_chart(fig, width="stretch")

elif secao == "Cobertura":
    cobertura = data.cobertura(catalogo)

    st.subheader("Cobertura de idPartido por legislatura")
    st.caption(
        "Indicador da base de dados carregada. NULL = par (deputado × legislatura) "
        "sem registro na API; o método inclui titulares e suplentes em todas as "
        "legislaturas (49ª–57ª)."
    )
    tabela = cobertura.copy()
    tabela["percentual"] = tabela["percentual"].map(lambda x: f"{x:.1f}%")
    st.dataframe(
        tabela.rename(columns={
            "idLegislatura": "Legislatura",
            "total": "Total",
            "com_partido": "Com partido",
            "sem_partido": "Sem partido",
            "percentual": "% com partido",
        }),
        hide_index=True,
        width="stretch",
    )

    fig = px.bar(
        cobertura, x="idLegislatura", y="percentual",
        text=cobertura.percentual.map(lambda x: f"{x:.1f}%"),
        labels={"idLegislatura": "Legislatura", "percentual": "% com partido"},
    )
    fig.update_xaxes(type="category")
    fig.update_yaxes(range=[0, 100])
    st.plotly_chart(fig, width="stretch")
