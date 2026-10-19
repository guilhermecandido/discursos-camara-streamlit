# Discursos Parlamentares — Câmara dos Deputados

Aplicação **somente leitura** (Streamlit) para explorar 661.514 discursos das
49ª–57ª legislaturas (1991–2027), coletados da API de Dados Abertos da Câmara
dos Deputados.

**App:** https://discursos-parlamentares.streamlit.app/

Este repositório é **independente**: contém apenas o aplicativo e um
**snapshot congelado em Parquet**. Não há scripts de coleta, credenciais nem
serviço de dados — o app lê os arquivos de `dados/` diretamente.

## Estrutura

```
dados/                snapshot Parquet (catálogos, transcrições, temas, índices, manifest)
web/app.py            interface Streamlit
web/data.py           leitura do snapshot Parquet
requirements.txt      dependências pinadas
.streamlit/config.toml
```

## Busca temática

Acima da tabela (abas **Discursos** e **Agregados**), a busca aplica-se ao
conjunto já filtrado:

- termos separados são combinados com **E**; `"frase exata"` entre aspas;
  acentos e maiúsculas são ignorados; não há OR, negação nem curingas;
- por padrão, busca em **temas** (palavras-chave e sumário);
- **Incluir texto integral** estende a busca à transcrição, disponível apenas
  na 51ª–57ª (pode levar alguns segundos; há progresso por bloco);
- Enter ou **Buscar** aplicam a consulta; **Limpar busca** volta ao conjunto
  filtrado;
- durante a busca, a coluna **Sumário** vira **Trecho**, com o trecho do match
  (texto integral, palavra-chave ou sumário), sem criar coluna nova.

## Rodar localmente

```bash
pip install -r requirements.txt
streamlit run web/app.py
```

Abra o endereço exibido no terminal (porta padrão 8501).

## Snapshot

- 31 arquivos, **~507 MB** (compressão zstd):
  - 9 catálogos (`catalogo_L49.parquet` … `catalogo_L57.parquet`) com data,
    deputado, partido, legislatura, tipo, sumário (400 caracteres) e link;
  - 11 blocos de transcrição (`transcricoes_L51_*.parquet` … `L57_*`) com
    texto integral, palavras-chave e sumário;
  - `temas.parquet` (palavras-chave originais e normalizadas por discurso) e
    9 índices invertidos `indice_L49.parquet` … `indice_L57.parquet`
    (termo → discurso; 12,76 milhões de postings, 62.492 termos);
  - `metadados.parquet` (legislaturas, partidos, período) e `manifest.json`
    (contagens, faixas de id, tamanhos e sha256).
- 661.514 discursos; **513.648** com transcrição; cobertura de partido
  **99,706%**.
- O app carrega o catálogo em 1–2 s e monta cada página em milissegundos; o
  texto do detalhe é lido apenas no bloco da legislatura selecionada.

## Fonte e atribuição

Dados: [Dados Abertos da Câmara dos Deputados](https://dadosabertos.camara.leg.br/).
Os textos são de domínio público; a atribuição à fonte é obrigatória.

## Limitações conhecidas

- 49ª e 50ª legislaturas não têm transcrição na fonte; o detalhe mostra
  "Sem transcrição" e o sumário truncado em 400 caracteres.
- 29 pares (deputado × legislatura) sem registro de partido na API → 1.944
  discursos com `idPartido` NULL.
- 157 registros irrecuperáveis (HTTP 500 da API) e 1 par sem resposta.
- 6 nomes de deputado NULL apenas em legislaturas fora do escopo.
- A busca por temas depende das palavras-chave da fonte (variações e ruído) e
  do sumário truncado em 400 caracteres; frases que cruzam esse corte não
  casam. O texto integral cobre só a 51ª–57ª.
- O snapshot é congelado: atualizações exigem gerar e publicar um novo
  snapshot (novo commit); não há atualização em tempo de execução.

## Atualizar o snapshot

O snapshot é gerado a partir da fonte oficial, conferido (contagens, hashes e
smoke test) e publicado como um novo commit. O Streamlit Cloud reinicia o app
com os dados novos.

## Licença

Código: uso acadêmico (TCC). Dados: Câmara dos Deputados.
