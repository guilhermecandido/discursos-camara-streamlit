"""Camada de dados somente-leitura da interface (snapshot Parquet congelado).

O aplicativo não conhece banco de dados: lê apenas os arquivos Parquet em
`dados/` (catálogos por legislatura, blocos de transcrição, metadados e
manifesto). O catálogo de discursos é carregado uma vez e mantido em memória;
filtros, paginação, ordenação, agregados e cobertura rodam em pandas/numpy.
O detalhe resolve a legislatura pelo catálogo e lê apenas o bloco de
transcrição correspondente.

Variável de ambiente:
    DADOS_DIR   pasta do snapshot (padrão: <raiz do projeto>/dados)

Somente leitura. Nenhum acesso a rede ou a servidor de dados.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import date, datetime, time as hora, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
DADOS_DIR = Path(os.environ.get("DADOS_DIR") or (RAIZ / "dados")).resolve()

_manifesto: dict | None = None
_catalogo: "Catalogo | None" = None


@dataclass(frozen=True)
class Filtros:
    legislaturas: tuple[int, ...] = ()
    partidos: tuple[int, ...] = ()
    incluir_sem_partido: bool = False
    data_inicio: date | None = None
    data_fim: date | None = None
    deputado: str = ""
    tipos: tuple[str, ...] = ()


@dataclass
class Catalogo:
    """Colunas de listagem em memória + vetores prontos para filtro."""

    df: pd.DataFrame
    leg: np.ndarray
    partido_id: np.ndarray      # -1 = sem partido
    data: np.ndarray
    deputado_id: np.ndarray
    nome: np.ndarray
    tipo: np.ndarray
    ano: np.ndarray
    sigla: np.ndarray
    url: np.ndarray
    id_discurso: np.ndarray
    origem: str
    segundos: float
    carregado_em: datetime
    nome_busca: pd.Series | None = None  # nomes em minúsculas (busca)
    # índice idDiscurso -> posição (construído sob demanda)
    ids_ord: np.ndarray | None = None
    ordem: np.ndarray | None = None


def manifesto() -> dict:
    """Manifesto do snapshot (carregado uma vez por processo)."""
    global _manifesto
    if _manifesto is None:
        caminho = DADOS_DIR / "manifest.json"
        if not caminho.exists():
            raise RuntimeError(f"Snapshot ausente: {caminho} não existe.")
        _manifesto = json.loads(caminho.read_text(encoding="utf-8"))
    return _manifesto


def gerado_em() -> date | None:
    """Data de geração do snapshot (ou None se o manifesto não a tiver)."""
    valor = str(manifesto().get("gerado_em", ""))[:10]
    try:
        return datetime.strptime(valor, "%Y-%m-%d").date()
    except ValueError:
        return None


def _chunks_por_legislatura() -> dict[int, list[dict]]:
    chunks: dict[int, list[dict]] = {}
    for arquivo in manifesto().get("arquivos", []):
        if arquivo.get("tipo") == "transcricao":
            chunks.setdefault(int(arquivo["legislatura"]), []).append(arquivo)
    for lista in chunks.values():
        lista.sort(key=lambda a: (a["min_id"], a["max_id"]))
    return chunks


def _ler_metadados() -> pd.DataFrame:
    return pd.read_parquet(DADOS_DIR / "metadados.parquet")


def _carregar_parquet() -> pd.DataFrame:
    partes = []
    for leg in range(49, 58):
        caminho = DADOS_DIR / f"catalogo_L{leg}.parquet"
        if not caminho.exists():
            raise RuntimeError(f"Catálogo ausente: {caminho}")
        partes.append(pd.read_parquet(caminho))
    return pd.concat(partes, ignore_index=True)


def _montar_catalogo(df: pd.DataFrame, origem: str, segundos: float) -> Catalogo:
    df = df.sort_values(
        ["dataHoraInicio", "idDiscurso"], ascending=False, ignore_index=True)
    df["idLegislatura"] = df["idLegislatura"].astype("int16")
    df["idDeputado"] = df["idDeputado"].astype("int32")
    df["idDiscurso"] = df["idDiscurso"].astype("int32")
    df["dataHoraInicio"] = pd.to_datetime(
        df["dataHoraInicio"]).astype("datetime64[us]")
    df["sumario"] = df["sumario"].fillna("")

    return Catalogo(
        df=df,
        leg=df["idLegislatura"].to_numpy(),
        partido_id=df["idPartido"].fillna(-1).astype("int32").to_numpy(),
        data=df["dataHoraInicio"].to_numpy(),
        deputado_id=df["idDeputado"].to_numpy(),
        nome=df["deputado"].to_numpy(),
        tipo=df["tipoDiscurso"].fillna("").to_numpy(),
        ano=df["dataHoraInicio"].dt.year.astype("int16").to_numpy(),
        sigla=df["partido"].fillna("(Sem partido)").to_numpy(),
        url=df["urlTexto"].fillna("").to_numpy(),
        id_discurso=df["idDiscurso"].to_numpy(),
        origem=origem,
        segundos=segundos,
        carregado_em=datetime.now(),
        nome_busca=df["deputado"].fillna("").astype(str).str.lower(),
    )


def carregar_catalogo() -> Catalogo:
    """Carrega o catálogo do snapshot e prepara os vetores de filtro."""
    global _catalogo
    inicio = time.perf_counter()
    cat = _montar_catalogo(
        _carregar_parquet(), "parquet", time.perf_counter() - inicio)
    _catalogo = cat
    return cat


def filtrar(cat: Catalogo, filtros: Filtros) -> np.ndarray:
    """Posições (ordem global, data DESC) que atendem aos filtros."""
    mascara = np.ones(len(cat.leg), dtype=bool)

    if filtros.legislaturas:
        mascara &= np.isin(cat.leg, np.asarray(filtros.legislaturas, dtype=np.int16))

    if filtros.partidos or filtros.incluir_sem_partido:
        if filtros.partidos:
            selecao = np.isin(
                cat.partido_id, np.asarray(filtros.partidos, dtype=np.int32))
        else:
            selecao = np.zeros(len(cat.leg), dtype=bool)
        if filtros.incluir_sem_partido:
            selecao |= cat.partido_id < 0
        mascara &= selecao

    if filtros.data_inicio:
        limite = np.datetime64(datetime.combine(filtros.data_inicio, hora.min))
        mascara &= cat.data >= limite
    if filtros.data_fim:
        limite = np.datetime64(
            datetime.combine(filtros.data_fim + timedelta(days=1), hora.min))
        mascara &= cat.data < limite

    texto = filtros.deputado.strip()
    if texto:
        if texto.isdigit():
            mascara &= cat.deputado_id == int(texto)
        else:
            mascara &= cat.nome_busca.str.contains(
                texto.lower(), regex=False).to_numpy()

    if filtros.tipos:
        mascara &= np.isin(cat.tipo, np.asarray(filtros.tipos, dtype=object))

    return np.flatnonzero(mascara)


def montar_pagina(cat: Catalogo, posicoes: np.ndarray,
                  offset: int, limite: int) -> pd.DataFrame:
    """Recorta a página (o sumário já está no catálogo, truncado em 400)."""
    indices = posicoes[int(offset):int(offset) + int(limite)]
    return cat.df.iloc[indices].copy()


def agregados(cat: Catalogo, filtros: Filtros) -> dict[str, pd.DataFrame]:
    """Agregações em memória sobre o recorte filtrado."""
    posicoes = filtrar(cat, filtros)
    if posicoes.size == 0:
        return {
            "partido": pd.DataFrame(columns=["partido", "discursos"]),
            "legislatura": pd.DataFrame(columns=["idLegislatura", "discursos"]),
            "ano": pd.DataFrame(columns=["ano", "discursos"]),
            "deputados": pd.DataFrame(columns=["deputado", "discursos"]),
        }

    siglas, quantos_partido = np.unique(cat.sigla[posicoes], return_counts=True)
    ordem = np.argsort(-quantos_partido)
    por_partido = pd.DataFrame({
        "partido": siglas[ordem], "discursos": quantos_partido[ordem]})

    legs, quantos = np.unique(cat.leg[posicoes], return_counts=True)
    por_legislatura = pd.DataFrame({
        "idLegislatura": legs.astype(int), "discursos": quantos})

    anos, quantos_ano = np.unique(cat.ano[posicoes], return_counts=True)
    por_ano = pd.DataFrame({"ano": anos.astype(int), "discursos": quantos_ano})

    ids, primeira, contagens = np.unique(
        cat.deputado_id[posicoes], return_index=True, return_counts=True)
    melhores = np.argsort(-contagens)[:15]
    por_deputado = pd.DataFrame({
        "deputado": cat.nome[posicoes[primeira[melhores]]],
        "discursos": contagens[melhores],
    })
    return {
        "partido": por_partido,
        "legislatura": por_legislatura,
        "ano": por_ano,
        "deputados": por_deputado,
    }


def cobertura(cat: Catalogo) -> pd.DataFrame:
    """Cobertura de idPartido por legislatura (estado do catálogo)."""
    legs, totais = np.unique(cat.leg, return_counts=True)
    com_partido = np.array([
        int((cat.partido_id[cat.leg == leg] >= 0).sum()) for leg in legs])
    df = pd.DataFrame({
        "idLegislatura": legs.astype(int),
        "total": totais,
        "com_partido": com_partido,
    })
    df["sem_partido"] = df["total"] - df["com_partido"]
    df["percentual"] = (df["com_partido"] / df["total"] * 100).round(1)
    return df


def _texto(valor) -> str:
    """Normaliza células de texto do Parquet (NULL -> '')."""
    if valor is None or (isinstance(valor, float) and np.isnan(valor)):
        return ""
    try:
        if pd.isna(valor):
            return ""
    except (TypeError, ValueError):
        pass
    return str(valor)


def _posicao_id(cat: Catalogo, id_discurso: int) -> int | None:
    """Posição do id no catálogo (índice ordenado, construído uma vez)."""
    if cat.ids_ord is None:
        cat.ordem = np.argsort(cat.id_discurso, kind="stable")
        cat.ids_ord = cat.id_discurso[cat.ordem]
    i = int(np.searchsorted(cat.ids_ord, int(id_discurso)))
    if i >= len(cat.ids_ord) or int(cat.ids_ord[i]) != int(id_discurso):
        return None
    return int(cat.ordem[i])


def detalhar(id_discurso: int):
    """Linha completa (metadados do catálogo + texto do bloco da legislatura)."""
    cat = _catalogo
    if cat is None:
        raise RuntimeError("Catálogo não carregado: chame carregar_catalogo().")
    posicao = _posicao_id(cat, id_discurso)
    if posicao is None:
        return None
    linha = cat.df.iloc[posicao]
    leg = int(linha.idLegislatura)

    transcricao = ""
    keywords = ""
    sumario = _texto(linha.sumario)
    tem_texto = False
    for chunk in _chunks_por_legislatura().get(leg, []):
        if chunk["min_id"] <= int(id_discurso) <= chunk["max_id"]:
            caminho = DADOS_DIR / chunk["nome"]
            trecho = pd.read_parquet(
                caminho,
                columns=["idDiscurso", "transcricao", "keywords", "sumario",
                         "tem_texto"],
                filters=[("idDiscurso", "==", int(id_discurso))],
            )
            if trecho.empty:
                continue
            registro = trecho.iloc[0]
            transcricao = _texto(registro.transcricao)
            keywords = _texto(registro.keywords)
            sumario = _texto(registro.sumario) or sumario
            tem_texto = bool(registro.tem_texto)
            break

    return pd.Series({
        "idDiscurso": int(linha.idDiscurso),
        "dataHoraInicio": linha.dataHoraInicio,
        "deputado": linha.deputado,
        "idDeputado": int(linha.idDeputado),
        "partido": None if pd.isna(linha.partido) else linha.partido,
        "idPartido": None if pd.isna(linha.idPartido) else int(linha.idPartido),
        "idLegislatura": leg,
        "tipoDiscurso": linha.tipoDiscurso,
        "transcricao": transcricao,
        "keywords": keywords,
        "sumario": sumario,
        "urlTexto": linha.urlTexto,
        "tem_texto": tem_texto,
    })


def listar_legislaturas() -> pd.DataFrame:
    meta = _ler_metadados()
    legs = meta[meta["tipo"] == "legislatura"].copy()
    legs["idLegislatura"] = legs["idLegislatura"].astype(int)
    legs["dataInicio"] = pd.to_datetime(legs["dataInicio"])
    legs["dataFim"] = pd.to_datetime(legs["dataFim"])
    return legs[["idLegislatura", "dataInicio", "dataFim", "rotulo"]] \
        .sort_values("idLegislatura").reset_index(drop=True)


def listar_partidos() -> pd.DataFrame:
    meta = _ler_metadados()
    partidos = meta[meta["tipo"] == "partido"].copy()
    partidos["idPartido"] = partidos["idPartido"].astype(int)
    return partidos[["idPartido", "sigla", "nome"]] \
        .sort_values("sigla").reset_index(drop=True)


def periodo_disponivel():
    """Intervalo das legislaturas 49-57 (metadados, sem varrer discurso)."""
    meta = _ler_metadados()
    periodo = meta[meta["tipo"] == "periodo"].iloc[0]
    return (pd.Timestamp(periodo.periodoInicio).date(),
            pd.Timestamp(periodo.periodoFim).date())
