# Instalar sem terminal

Para usar o Vagalume no Windows ou no macOS sem digitar comandos. Tudo depois da instalação acontece no navegador: buscar candidatas, revisar, treinar, gerar as fichas e enviar ao VSX.

O app nunca foi usado de verdade no Windows nem no macOS, embora os testes automáticos rodem nos dois a cada mudança. Se algo der errado, abra uma conversa em [Discussões](https://github.com/mpena2099/vagalume/discussions) com a mensagem que apareceu na janela.

## 1. Instale o Python

Baixe o Python 3.10 ou mais novo em [python.org/downloads](https://www.python.org/downloads/) e instale.

- **Windows:** na primeira tela do instalador, marque **"Add python.exe to PATH"** antes de clicar em **Install Now**. Sem isso, o iniciador não acha o Python.
- **macOS:** abra o arquivo `.pkg` baixado e siga as telas.

## 2. Baixe o Vagalume

Na [página do projeto no GitHub](https://github.com/mpena2099/vagalume), clique em **Code** e depois em **Download ZIP**. Descompacte o ZIP numa pasta sua, por exemplo `Documentos/vagalume`. Evite deixar dentro de Downloads, que costuma ser limpa, e em pasta sincronizada com nuvem (OneDrive, iCloud), que atrapalha o banco de dados.

## 3. Abra com dois cliques

Dentro da pasta:

- **Windows:** clique duas vezes em `iniciar_vagalume.bat`. Se aparecer o aviso azul "O Windows protegeu o computador", clique em **Mais informações** e depois em **Executar assim mesmo**.
- **macOS:** clique com o botão direito em `iniciar_vagalume.command` e escolha **Abrir** (na primeira vez, o clique duplo é bloqueado porque o arquivo veio da internet). Confirme em **Abrir** no aviso. Se o macOS disser que não tem permissão, abra o Terminal uma única vez e rode `chmod +x ` seguido do arquivo arrastado para a janela.

Na primeira vez, uma janela preta mostra a instalação das bibliotecas, que leva alguns minutos e precisa de internet. Depois o navegador abre sozinho no app. Das próximas vezes ele abre direto.

**Deixe essa janela aberta enquanto usa o app.** Fechar a janela fecha o app. Uma busca de candidatas já iniciada continua rodando mesmo assim.

## 4. Primeiro uso

1. Na página **Revisão**, abra **Buscar novas candidatas** na barra lateral e clique em **Buscar mais candidatas** (duas vezes, para confirmar). A busca escolhe sozinha uma região do céu, baixa as curvas do TESS e leva de 1 a 2 horas.
2. Enquanto isso, treine o olho na [demo online](https://vagalume.streamlit.app). Os casos de treino locais aparecem na página **Treino** quando a primeira busca termina.
3. Quando a busca terminar, as candidatas aparecem na **Revisão**. Daí em diante, siga o [passo a passo](comecar.md).

## Atualizar

Baixe o ZIP de novo e descompacte por cima da pasta antiga. A pasta `data/`, com as suas revisões e fichas, e a pasta `venv/` são mantidas. Se a nova versão pedir bibliotecas novas, apague o arquivo `venv/.instalado` antes de abrir: o iniciador reinstala.

## Se der errado

| O que aparece | O que fazer |
|---|---|
| "Python não encontrado" | Instale o Python (passo 1). No Windows, reinstale marcando "Add python.exe to PATH" |
| A instalação para com erro | Confira a internet e abra o iniciador de novo: ele retoma |
| O navegador não abre | Abra à mão o endereço que a janela mostra (`http://localhost:8501`) |
| A janela fecha sozinha logo ao abrir | Rode o iniciador pelo Terminal (ou Prompt de Comando) para ver a mensagem e mande-a em Discussões |
