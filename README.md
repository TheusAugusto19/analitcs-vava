# Analytics Vava

Analytics de partidas de Valorant, Minecraft, CS e Xadrez. O banco de dados é o `placar.json`.

## Editar (no PC)
```
python server.py
```
Abra http://localhost:8000, responda "Quem é você?" com nome e PIN e registre as partidas. Depois envie o `placar.json` (e a pasta `fotos/`) para o GitHub.

## Online (GitHub Pages)
Settings → Pages → Deploy from a branch → `main` / `(root)`.

Para editar pelo site online, cole um token do GitHub em **Editar online**, na barra lateral.
O token fica salvo só no navegador e cada edição atualiza o `placar.json` direto no repositório.

Criar o token: GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens →
Repository access: só `analitcs-vava` → Permissions: Contents = Read and write.
