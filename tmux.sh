#!/bin/bash

SESSION="conexao_monstrinho"
PROJECT_DIR="/home/pi/MDIS/mdis"
PYTHON="$PROJECT_DIR/venv/bin/python"
SCRIPT="$PROJECT_DIR/main.py"

if tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "⚠️ A sessão '$SESSION' já está em execução."
else
    echo "🚀 Iniciando sessão '$SESSION'..."

    tmux new-session -d -s "$SESSION" \
    "cd $PROJECT_DIR && $PYTHON $SCRIPT; echo ''; echo '⚠️ Processo finalizado. Pressione Ctrl+B depois D para sair do tmux.'; exec bash"

    echo "✅ Sessão '$SESSION' criada."
fi

tmux attach -t "$SESSION"