# Uso

## Passo a passo

1. **Instale** o ambiente (comandos logo abaixo) e rode o pipeline: `python -u pipeline.py` no campo padrão ou `--proximo` para um campo novo. Leva de 1 a 2 horas.
2. **Treine** no app (`python iniciar.py`, página Treino) até acertar uns 80% das últimas 20. O treino usa estrelas já conhecidas e mostra a resposta depois de cada caso.
3. **Revise a fila** no app: Confirmar, Dúvida ou Descartar em cada candidata. Os casos óbvios (pico do sinal a mais de 2 pixels do alvo, ou fora do alvo e sem repetir em outros setores) já saem descartados, com o motivo e um botão para rever. Veja [como classificar](revisao.md#revisao-visual-como-classificar).
4. **Gere as fichas do VSX** (Fase 8) no app: com a fila revisada, o botão **Gerar fichas do VSX** no topo da página Fichas; a opção "Incluir as marcadas como dúvida" faz o mesmo que `--duvidas`. O mesmo comando continua valendo no terminal: `python -u src/ficha_vsx.py`. Ela leva alguns minutos por estrela, mostra o progresso e, ao terminar, grava `data/vsx/fichas.md`, com o que o formulário do VSX pede, e a curva em fase de cada uma (`data/vsx/<tic>_fase.png`). Rodar de novo retoma: a ficha pronta é mantida e a incompleta refaz só a busca que faltou (Gaia ou VizieR); `--refazer` refaz tudo. Com o VizieR de Estrasburgo fora do ar, a busca no VizieR é feita só numa lista de catálogos de variáveis num espelho, e a ficha avisa isso sem impedir a submissão; quando ele volta, a página Fichas refaz sozinha a busca completa. A Fase 8 também resolve sozinha as conferências que os dados permitem: a vizinha suspeita de blend (pelo pixel do pico do sinal), o período (instante do mínimo em cada setor, com o período refinado quando todos alinham) e um tipo provável pelo Gaia (temperatura e gravidade) quando a ficha sugere mais de um.
5. **Confira cada estrela na página Fichas**: a tabela diz o que falta em cada uma, e a aba Conferir consulta o VSX online sozinha pelas coordenadas (se alguém a submeteu antes, a ficha bloqueia) e mostra o tipo provável para você confirmar. Ela também dá o veredito: **"Pode enviar"**, com a lista do que foi conferido (ficha, VSX ao vivo, anexos e limite de submissões), ou **"Ainda não envie"**, com o próximo passo. Na tabela, "Pronta" quer dizer que não falta nada.
6. **Submeta**, uma estrela por vez, pelo **New Star Wizard** do VSX (usuário novo só pode ter uma submissão até a primeira ser aceita; enquanto isso, a página Fichas mostra as outras como "Aguardar o VSX"): crie o login em vsx.aavso.org (menu **Register**, separado da conta do site da AAVSO), entre, abra **Submit** e copie os campos da página Fichas. O passo a passo, com a correspondência entre cada campo da ficha e o do formulário, está em [submeter_vsx.md](submeter_vsx.md). A moderação costuma levar semanas.
7. **Marque "Enviada ao VSX"** na aba Enviar da estrela, na página Fichas. O aceite é automático: quando a estrela aparece no VSX, a página marca "Aceita" e anota o nome que ela recebeu. A trilha da Revisão mostra quantas confirmadas já foram enviadas e aceitas.
8. **Busque mais candidatas** (expander "Buscar novas candidatas", na barra lateral da Revisão, ou `python -u pipeline.py --proximo`) e volte ao passo 3.

## Comandos

```bash
python3 -m venv venv && source venv/bin/activate   # Linux e macOS
pip install -r requirements.txt
python -u pipeline.py           # campo fixo do config.py (fases 1 a 7 e casos do treino)
python -u pipeline.py --proximo # escolhe sozinho o próximo campo do céu e roda tudo
python tests/test_units.py      # testes offline (ou pytest)
python iniciar.py               # revisão visual das candidatas (usa o venv sozinho; --demo abre só o treino)
python src/ficha_vsx.py         # Fase 8: fichas do VSX das confirmadas (--duvidas, --todas, --refazer)
```

Sem terminal (Windows ou macOS): baixe o ZIP e clique duas vezes em `iniciar_vagalume.bat` (Windows) ou `iniciar_vagalume.command` (macOS); na primeira vez ele instala tudo sozinho. Passo a passo em [Instalar sem terminal](instalar.md).

No Windows (PowerShell), crie e ative o ambiente assim; o resto dos comandos é igual:

```powershell
py -m venv venv; venv\Scripts\Activate.ps1
```


`-u` faz o Python escrever cada `print` na hora. No terminal isso já acontece, mas com a saída redirecionada (`> log.txt`, `| tee log.txt`, `nohup`) o Python junta tudo em blocos e o log fica parado por minutos, parecendo travado, nas fases longas.

**Mais candidatas.** Terminou de revisar as candidatas da fila? O expander "Buscar novas candidatas", na barra lateral da Revisão, abre sozinho e mostra o botão "Buscar mais candidatas", que pede confirmação antes de começar, e depois o progresso da busca, com um botão para cancelar; pelo terminal, o mesmo é `python -u pipeline.py --proximo`. A busca escolhe sozinho uma região do céu ainda não varrida, no plano da Via Láctea e coberta por um setor do TESS com cadência de 200 s, e roda tudo, inclusive os casos novos do treino (1 a 2 horas para 600 estrelas). As candidatas novas entram na fila do app junto com as antigas. As regiões já feitas ficam na tabela `campos_feitos`; uma rodada que falha no meio não conta e é refeita na próxima vez. A grade tem mais de mil regiões. Se um dia acabar, o comando avisa e não faz nada.

As decisões da revisão ficam na tabela `revisao_humana`, que o pipeline nunca recria. O app usa o tema escuro de `.streamlit/config.toml` e o visual de `app/estilo.py`; as páginas ficam em `app/paginas/`.

As curvas baixadas ficam em cache em `data/curvas/` e as figuras de triagem em `data/triagem/`.
