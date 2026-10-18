"""Interface Streamlit de exploração dos discursos parlamentares (somente leitura).

Lê o snapshot Parquet em `dados/` (ou em `DADOS_DIR`):
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
    page_icon="🏛️",
    layout="wide",
)


@st.cache_resource(show_spinner=False)
def carregar_catalogo():
    """Catálogo em memória (uma carga por processo)."""
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

DEFAULTS = {
    "f_legs": [57],
    "f_partidos": [],
    "f_sem_partido": False,
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
    "Partido registrado na legislatura (deputado × legislatura); NULL apenas "
    "quando não há registro para o par. Fonte: Dados Abertos da Câmara, "
    "49ª–57ª legislaturas."
)

with st.sidebar:
    st.header("Filtros")

    legislaturas_sel = st.multiselect(
        "Legislatura(s)",
        options=legislaturas.idLegislatura.tolist(),
        format_func=lambda x: rotulo_leg.get(x, str(x)),
        key="f_legs",
        help="Padrão: 57ª. Selecione outras para ampliar o período.",
    )

    partidos_sel = st.multiselect(
        "Partido(s)",
        options=partidos.idPartido.tolist(),
        format_func=lambda x: rotulo_partido.get(x, str(x)),
        key="f_partidos",
        help="Vazio = todos os partidos. A semântica é 'partido registrado na legislatura'.",
    )
    st.checkbox("Incluir 'Sem partido'", key="f_sem_partido")

    datas = st.date_input(
        "Intervalo de datas",
        min_value=inicio,
        max_value=fim,
        key="f_datas",
        help="Filtra dataHoraInicio; o dia final é incluído.",
    )

    st.text_input(
        "Deputado (nome ou ID)",
        key="f_deputado",
        placeholder="ex.: MICHEL TEMER ou 73552",
    )

    st.checkbox("Filtrar por tipo de discurso", key="f_tipo_on")
    if st.session_state["f_tipo_on"]:
        st.multiselect("Tipo(s) de discurso", options=tipos_disponiveis, key="f_tipos")

    st.divider()
    gerado = data.gerado_em()
    gerado_txt = f"{gerado:%d/%m/%Y}" if gerado else "data indisponível"
    st.caption(
        f"Snapshot de {gerado_txt} · {len(catalogo.df):,} discursos · "
        f"carga {catalogo.segundos:.1f} s".replace(",", ".")
    )
    st.caption(
        "Somente leitura. Snapshot congelado: os dados não mudam enquanto "
        "o app estiver no ar."
    )

if isinstance(datas, (tuple, list)) and len(datas) == 2:
    data_inicio, data_fim = datas
elif isinstance(datas, (tuple, list)) and len(datas) == 1:
    data_inicio, data_fim = datas[0], datas[0]
else:
    data_inicio, data_fim = inicio, fim

filtros = data.Filtros(
    legislaturas=tuple(legislaturas_sel),
    partidos=tuple(partidos_sel),
    incluir_sem_partido=st.session_state["f_sem_partido"],
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
    if filtros.partidos:
        partes.append("Partido: " + ", ".join(
            sigla_partido.get(x, str(x)) for x in filtros.partidos))
    if filtros.incluir_sem_partido:
        partes.append("+ Sem partido")
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
    ["Discursos", "Agregados", "Cobertura", "Sobre"],
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
    """Paginação abaixo da tabela: Anterior/Próxima + página editável inline."""
    esquerda, centro, direita = st.columns([1, 4, 1], vertical_alignment="center")
    esquerda.button(
        "◀ Anterior",
        disabled=pagina <= 1,
        on_click=lambda: st.session_state.update(
            f_pagina=max(1, st.session_state["f_pagina"] - 1)),
        width="stretch",
    )
    primeiro = min(offset + 1, total) if total else 0
    ultimo = min(offset + tamanho, total)

    with centro:
        # Mantém o campo alinhado quando a página muda por Anterior/Próxima.
        if st.session_state.get("f_pagina_input") != str(pagina):
            st.session_state["f_pagina_input"] = str(pagina)
        c1, c2, c3 = st.columns([1, 1, 3], vertical_alignment="center")
        c1.markdown(
            "<div style='text-align:right'>Página</div>",
            unsafe_allow_html=True,
        )
        c2.text_input(
            "Página",
            key="f_pagina_input",
            label_visibility="collapsed",
            on_change=ir_para_pagina,
            args=(max_pag,),
        )
        c3.markdown(
            f"de <b>{max_pag}</b> · {primeiro:,}–{ultimo:,} de {total:,}"
            .replace(",", "."),
            unsafe_allow_html=True,
        )

    direita.button(
        "Próxima ▶",
        disabled=pagina >= max_pag,
        on_click=lambda: st.session_state.update(
            f_pagina=min(max_pag, st.session_state["f_pagina"] + 1)),
        width="stretch",
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
            st.subheader("Top deputados")
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
        "Indicador do snapshot carregado. NULL = par (deputado × legislatura) "
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

elif secao == "Sobre":
    st.subheader("Semântica dos dados")
    st.markdown(
        """
- **Partido registrado na legislatura**: `discurso.idPartido` vem do registro
  de partido por (deputado × legislatura) em `filiacao` (evento "Partido no
  início da legislatura" do `/historico`). Inclui titulares e suplentes; em
  legislaturas encerradas reflete o último partido do deputado na legislatura.
- **NULL** significa apenas que não há registro para o par
  (deputado × legislatura) na API.
- A interface apenas lê `discurso.idPartido` já carimbado; não recalcula
  partido a partir de `filiacao`.
- Filtro por deputado: nome (contém) ou ID numérico exato.
- Datas referem-se a `dataHoraInicio`; o dia final é incluído.
- A coluna **Fonte** é o link para a página original da Câmara; o **texto
  integral** é a transcrição exibida no detalhe do discurso.
        """
    )
    st.subheader("Arquitetura e desempenho")
    gerado = data.gerado_em()
    gerado_txt = f"{gerado:%d/%m/%Y}" if gerado else "data indisponível"
    st.markdown(
        f"""
- **Snapshot congelado em Parquet** (gerado em {gerado_txt}): catálogos por
  legislatura, transcrições em blocos e metadados pequenos.
- O catálogo de {len(catalogo.df):,} discursos (sumário truncado em 400
  caracteres, sem transcrição) é carregado **uma vez** e mantido em memória.
- Filtros, ordenação, paginação e agregados rodam em memória; o detalhe lê
  apenas o bloco de transcrição da legislatura do discurso.
- Estado atual: carga em **{catalogo.segundos:.1f} s**.
        """.replace(",", ".")
    )
    st.subheader("Limitações conhecidas")
    st.markdown(
        """
- **29 pares** (deputado × legislatura) sem registro na API, concentrados nas
  49ª/50ª; os discursos desses pares ficam com `idPartido` NULL. Veja a seção
  **Cobertura** para os números atuais.
- **157 registros** de discurso irrecuperáveis por HTTP 500 da API (0,024%) e
  **1 par** (deputado 160666/55ª) sem resposta; não afetam as consultas.
- **6 nomes** de deputado NULL apenas em legislaturas fora do escopo 49ª–57ª.
- **49ª e 50ª não têm transcrição na fonte**: o detalhe mostra "Sem
  transcrição" e o sumário **truncado em 400 caracteres**.
- **31.217 discursos** de 51ª–57ª têm transcrição vazia na origem; o detalhe
  mostra o sumário e as palavras-chave.
- O snapshot é **congelado**: mudanças na fonte só aparecem após gerar e
  publicar um novo snapshot.
        """
    )
    st.subheader("Como atualizar")
    st.markdown(
        "O snapshot é regenerado a partir da fonte oficial e publicado como um "
        "novo commit; o app reinicia com os dados novos:"
    )
    st.code(
        "# 1) exportação  -> gera dados/ (Parquet + manifest)\n"
        "# 2) conferência -> contagens, hashes e smoke test\n"
        "# 3) publicação  -> commit/push; o Streamlit Cloud reinicia",
        language="text",
    )
    st.caption(
        "O snapshot é a fonte de verdade do app; não há atualização em tempo "
        "de execução."
    )
