from sqlalchemy.orm import declarative_base

# O 'declarative_base' cria uma classe que funciona como um catálogo central
# para todos os seus modelos (tabelas) do banco de dados.
# Todas as classes que representam tabelas deverão herdar desta 'Base'.
Base = declarative_base()

# Por que isso é importante?
# 1. Registro: O SQLAlchemy usa a 'Base' para saber quais tabelas existem no seu código.
# 2. Tradução: Ela permite que você escreva classes Python que o SQLAlchemy 
#    converte automaticamente em comandos SQL (CREATE TABLE, etc.).