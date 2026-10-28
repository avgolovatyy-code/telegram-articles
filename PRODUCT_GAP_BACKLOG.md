# Product gap backlog — после реализации 3.0 (до live-verify)

P0/P1 закрыты в коде. Ниже — то, что **нельзя** честно пометить PASS без внешнего доступа или накопленной статистики.

| ID | Приоритет | Суть | Почему не закрыто кодом |
|---|---|---|---|
| SOURCE-03 | P2 | Live Google Trends / Wordstat | Нет авторизованного коннектора. Статус `UNAVAILABLE`, объёмы не выдумываются. |
| SOURCE-02 | P2 | Живая афиша музеев | Нет легального API. Events provider `PARTIAL`. |
| BRAND-01/02 | P1 live | getChat title/description/pin | Только на production после SSH. |
| PLAN-01 live | P1 live | Реальный OpenAI Chief Editor request id | Mock в CI; live — `wgt doctor` / editorial run на проде. |
| RELEASE-01 | P0 live | Фактический деплой SHA | После `deploy/from-agent.sh`. |
| ANAL-01 | P3 | 30-дневные метрики удержания | Наблюдательные, не day-one gate. |
| PUB-04 live | P2 | Новый live-пост каждого канала | Не слать dummy. `LIVE_NEW_POST=NOT_YET_OBSERVED`, если слот не подошёл. |

Не делаем: новые каналы, рост `DAILY_AI_BUDGET_USD`, массовая правка истории, выдуманные тренды.
