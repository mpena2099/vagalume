# Contribuindo com o Vagalume

Obrigado pelo interesse. O Vagalume é um projeto pessoal, então a revisão pode demorar. Issues, ideias e pull requests são bem-vindos.

## Boas contribuições

- Caso do treino cuja resposta pareça errada: mande o número do caso e o TIC. São estrelas já catalogadas, então o TIC pode aparecer.
- Catálogo de variáveis que a Fase 5 ainda não consulta, com o identificador do VizieR e a coluna de período. A lista fica em `CATALOGOS_VIZIER`, no `config.py`.
- Resultado de rodar um campo do céu novo (`python -u pipeline.py --proximo`): quantas estrelas, quantos sinais e quantas candidatas.
- Relato de uma submissão ao VSX: o que o moderador pediu, o que mudou na ficha, se foi aceita.
- Bug com o comando que você rodou, o erro completo, o sistema operacional e a versão do Python.

Antes de uma mudança grande, abra uma issue para combinarmos o rumo.

## Ambiente de desenvolvimento

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python tests/test_units.py
```

Os testes são offline e rodam em segundos. A Fase 1 (`python -c "from src.sanity_check import run; run()"`) é o teste de aceite com rede: ela redescobre três variáveis conhecidas e confere o período.

## Regras

- Siga o estilo do módulo que você está mexendo: cabeçalho curto, comentários que explicam o porquê, código e prints em português.
- Deixe a lógica pura fora da rede, para poder ser testada offline.
- Comportamento novo pede teste novo em `tests/test_units.py`.
- Teste do app com `streamlit.testing.v1.AppTest` só com `VAGALUME_DB` apontando para uma cópia do banco. Sem isso, o clique de teste vira revisão de verdade.
- O CI roda Linux, Windows e macOS, com Python 3.10 e 3.13.
- Um assunto por pull request, com uma descrição curta do que mudou e por quê.

> **Nunca publique uma candidata que ainda não foi submetida**, nem o TIC, nem a figura, nem as coordenadas, em issue, pull request, README ou figura de exemplo. O repositório é público, e isso entregaria a descoberta antes da submissão ao VSX.

## Licença

Ao contribuir, você concorda que a sua contribuição fica sob a licença MIT do projeto.
