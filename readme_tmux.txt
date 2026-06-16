execute o codigo abaixo para ativar sessão tmux

chmod +x tmux.sh
./tmux.sh
tmux attach -t conexao_monstrinho

////// COMANDOS ////

Sessões

tmux new -s nome → cria uma nova sessão com nome.

tmux ls → lista todas as sessões.

tmux attach -t nome → entra em uma sessão existente.

tmux detach (atalho: Ctrl+b d) → sair da sessão sem encerrá-la.

tmux kill-session -t nome → mata uma sessão.

tmux kill-server → encerra todas as sessões do tmux.

Janelas

Ctrl+b c → cria uma nova janela.

Ctrl+b , → renomeia a janela.

Ctrl+b w → lista janelas e permite escolher.

Ctrl+b n → vai para a próxima janela.

Ctrl+b p → vai para a janela anterior.

Ctrl+b & → fecha a janela atual.

Painéis (splits)

Ctrl+b % → divide verticalmente.

Ctrl+b " → divide horizontalmente.

Ctrl+b o → alterna entre painéis.

Ctrl+b ; → volta para o último painel usado.

Ctrl+b x → fecha o painel atual.

Ctrl+b z → maximiza/restaura o painel.

Ctrl+b { → move painel para esquerda.

Ctrl+b } → move painel para direita.

Ctrl+b ↑/↓/←/→ → muda de painel com setas.

Diversos úteis

Ctrl+b ? → mostra ajuda com todos os comandos.

Ctrl+b t → mostra um relógio no painel.

Ctrl+b : → entra no modo de comando.

Ctrl+b [ → entra no modo de cópia (permite rolar com setas ou PgUp).

Ctrl+b ] → cola o texto copiado.

tmux source-file ~/.tmux.conf → recarrega configurações.