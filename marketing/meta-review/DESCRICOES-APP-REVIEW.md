# App Review do Antares CRM — textos para a Meta

Cole cada texto no campo "Forneça uma descrição detalhada…" da permissão e envie o vídeo correspondente (pasta `out/`).
Antes de enviar, troque [SENHA] pela senha que você definiu para a conta meta-review (e o e-mail, se usou outro).
Não informe nenhuma credencial do Instagram (a própria Meta pede isso).

## instagram_business_basic — `out/antares-instagram_business_basic.mp4`

```
Antares CRM (https://antares.douglasgermano.com) is a web CRM for small businesses. We request instagram_business_basic because it is required by instagram_business_manage_messages and instagram_business_manage_comments, which we also request in this submission, and because we display the connected account inside the app.

How we use it: the business connects its own Instagram professional account through Instagram Business Login. We read the account ID, username, name and profile picture. They are shown in Settings > Connections so the user can confirm which account is connected. The account ID is used to route incoming messages and comments to the correct workspace and to tell the business's own messages apart from its customers' messages. We do not use this data for advertising and we do not share it with third parties. Disconnecting the account deletes the stored token.

How to test:
1. Open https://antares.douglasgermano.com/login and sign in with: Account: meta-review / Email: contato+metareview@douglasgermano.com / Password: [SENHA]
2. In the left menu, click "Configurações" (Settings), then the "Conexões" (Connections) tab.
3. In the Instagram card, click "Conectar Instagram" (Connect Instagram).
4. Sign in with your Instagram professional account and click "Allow".
5. You are redirected back to Antares. The Instagram card now shows the connected account's name, @username and profile picture, with the status "Conectado" (Connected).

The app interface is in Portuguese; the screencast includes English narration and captions.
```

## instagram_business_manage_messages — `out/antares-instagram_business_manage_messages.mp4`

```
Antares CRM gives small businesses a shared Inbox for customer conversations. With instagram_business_manage_messages, direct messages sent to the connected Instagram professional account are received through the Instagram messaging webhook and shown in the Antares Inbox (Instagram channel), linked to a contact record. A team member reads the conversation and replies manually from Antares. The reply is sent through the Instagram API only within the 24-hour messaging window. Antares does not send bulk, automated marketing or unsolicited messages on Instagram. This lets the business answer customers quickly without missing messages, and keeps the conversation history with the customer's record in the CRM.

How to test:
1. Sign in at https://antares.douglasgermano.com/login with: Account: meta-review / Email: contato+metareview@douglasgermano.com / Password: [SENHA]
2. Connect your Instagram professional account in "Configurações" (Settings) > "Conexões" (Connections) > "Conectar Instagram", as described for instagram_business_basic.
3. From a different Instagram account, send a direct message to the connected professional account.
4. In Antares, open "Caixa de entrada" (Inbox) in the left menu and set the channel filter to "Instagram". The new conversation appears at the top of the list.
5. Click the conversation, type a reply in the "Escreva sua resposta…" (Write your reply) box and click the send button. Antares shows "Resposta enviada" (Reply sent).
6. Open the conversation on Instagram: the reply sent from Antares is delivered there.

The app interface is in Portuguese; the screencast includes English narration and captions.
```

## instagram_business_manage_comments — `out/antares-instagram_business_manage_comments.mp4`

```
Antares CRM helps small businesses respond quickly to comments on their own Instagram posts. With instagram_business_manage_comments, comments on the connected account's media are received through the Instagram comments webhook. The business can create an automation that publishes a public reply to comments that match conditions it defines (for example, comments containing a keyword). The business controls the trigger conditions and the reply text. Each comment receives at most one automated reply, with a rate limit, and comments made by the account itself or replies to comments are ignored. We only read and reply to comments on media owned by the connected account.

How to test:
1. Sign in at https://antares.douglasgermano.com/login with: Account: meta-review / Email: contato+metareview@douglasgermano.com / Password: [SENHA]
2. Connect your Instagram professional account in "Configurações" (Settings) > "Conexões" (Connections) > "Conectar Instagram", as described for instagram_business_basic.
3. In the left menu, open "Automações" (Automations) and click "Nova automação" (New automation).
4. Enter any name. In "Gatilho" (Trigger), choose "Comentário no Instagram" (Instagram comment).
5. Click "Adicionar condição" (Add condition) and set: "Texto do comentário (Instagram)" (Comment text) / "Contém" (Contains) / "test".
6. In "Fazer isto" (Do this), set "Ação" (Action) to "Responder o comentário (Instagram)" (Reply to the comment) and type a reply text, for example "Thanks for your comment!".
7. Click "Salvar automação" (Save automation). The automation appears as active.
8. From a different Instagram account, comment "test" on any post of the connected professional account.
9. In Antares, open the "Execuções" (Runs) tab in Automations: the run appears with status "Concluída" (Completed).
10. Open the post on Instagram: the public reply from the business account appears under the comment.

The app interface is in Portuguese; the screencast includes English narration and captions.
```
