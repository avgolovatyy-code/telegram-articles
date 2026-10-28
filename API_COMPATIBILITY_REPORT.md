# API compatibility — 2026-10-28

Проверено по документации, без выдуманных SDK.

| API | Использование | Заметки |
|---|---|---|
| Telegram Bot API `sendRichMessage` | rich/museum | официальные блоки, URL-entity для футера |
| Telegram `sendMessage` / `sendPhoto` | короткие форматы | `parse_mode=HTML`, `disable_web_page_preview=true` для футера |
| Telegram `sendPoll` | EN native; RU fallback в один текст+футер | poll не несёт inline-ссылку |
| MAX `POST /messages` | HTML ≤4000 | футер в том же `text`; кнопки товаров отдельно |
| OpenAI Responses + JSON schema | Chief Editor / Writer / Critic | модели из env, не хардкод несуществующих имён |
| WeGoTrip Affiliate | каталог RU `.ru` / EN `.com` | `coupon=435` один раз, UTM только на товар |

Live-проверка ключей и chat_id — на production после деплоя (`wgt doctor`, `wgt check-max`).
