# Vozes da tela de boas-vindas

Cada voz tem uma pasta. Dentro dela, um mp3 por pessoa (nome em minúsculas, sem acento) e um `geral.mp3` para quem não tiver áudio próprio.

```
vozes/epaminondas/geral.mp3   "Seja bem-vindo. O que vai ser para hoje?"   (voz masculina)
vozes/epaminondas/lopes.mp3   "Seja bem-vindo, Lopes. O que vai ser para hoje?"
vozes/epaminondas/theus.mp3   "Seja bem-vindo, Theus. O que vai ser para hoje?"
vozes/clara/geral.mp3         (mesmas frases, voz feminina)
vozes/clara/lopes.mp3
vozes/clara/theus.mp3
```

Sem o mp3, o site usa a voz de leitura do navegador (não funciona no app do Discord).
Para enviar: no GitHub, abra a pasta da voz → Add file → Upload files.

## Créditos

Áudios atuais gerados com o [Piper](https://github.com/rhasspy/piper) usando a voz `pt-br-edresson-low`,
treinada com o [TTS-Portuguese-Corpus](https://github.com/Edresson/TTS-Portuguese-Corpus) (licença CC BY 4.0).
A Clara é a mesma voz com o tom ajustado. Para trocar, é só enviar outro mp3 com o mesmo nome.
