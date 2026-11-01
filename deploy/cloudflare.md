# Деплой на Cloudflare Workers

Бесплатный тариф Workers: 100 000 запросов в сутки, карта не нужна.

1. Зарегистрируйтесь на https://dash.cloudflare.com/sign-up.
2. Установите зависимости и войдите (откроется браузер):

   ```bash
   cd cloudflare
   npm install
   npx wrangler login
   ```

3. Задеплойте:

   ```bash
   npx wrangler deploy
   ```

   Wrangler напечатает адрес вида `https://pravo-mcp.<ваш-поддомен>.workers.dev`.
4. Проверьте:

   ```bash
   ../scripts/smoke.sh https://pravo-mcp.<ваш-поддомен>.workers.dev/mcp
   ```

5. В Claude: **Settings → Connectors → Add custom connector**, адрес
   `https://pravo-mcp.<ваш-поддомен>.workers.dev/mcp`.

Ответы портала кэшируются в Cloudflare: справочники сутки, карточки документов неделю, поиск 5 минут.
Логи: `npx wrangler tail`.
