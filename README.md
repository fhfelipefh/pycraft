# PyCraft

Um mini-jogo de blocos 3D feito em Python com [Ursina Engine](https://www.ursinaengine.org/).

## Visao Geral

PyCraft e um projeto simples inspirado em Minecraft, permitindo ao usuario construir e destruir blocos em um ambiente 3D.

## Requisitos

- Python 3.10+

## Instalacao

```bash
./scripts/setup.sh
```

O script cria `.venv/`, atualiza o `pip` e instala as dependencias do projeto.

## Como Executar

```bash
./run.sh
```

Alternativamente:

```bash
source .venv/bin/activate
python main.py
```

## Aceleracao Nativa (C++)

O modulo nativo C++ e obrigatorio para executar o jogo com desempenho aceitavel.

O `./scripts/setup.sh` ja compila automaticamente.

Compilacao manual (se necessario):

```bash
source .venv/bin/activate
cd native
python setup.py build_ext --inplace
cd ..
```

Se o modulo nao estiver disponivel, `./run.sh` encerra com erro orientando executar `./scripts/setup.sh`.

## Controles

- Colocar bloco: clique direito
- Destruir bloco: clique esquerdo
- Abrir menu: `Esc`
- Exibir/ocultar FPS: `F3`

## Configuracoes de Musica

No menu de configuracoes (`Esc` -> `Configuracoes`), agora e possivel:

- Ligar/desligar musica
- Aumentar e diminuir volume da musica
