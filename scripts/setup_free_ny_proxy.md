# 🗽 Гайд: 100% Безкоштовний US (New York) IP та Захист від Тіньового Бану

Цей посібник допоможе вам налаштувати стабільне та абсолютно **безкоштовне** підключення через New York IP для безпечного автозаливу контенту без ризику потрапляння в тіньовий бан (0 переглядів).

---

## 📌 1. Чому одні платформи залежні від IP, а інші — ні?

| Платформа | Чи потрібен US/NY IP? | Чому саме так? (Анти-Тіньовий бан) |
|---|:---:|---|
| **TikTok** | 🔴 **КРИТИЧНО** | Алгоритм TikTok оцінює IP, ASN (тип провайдера) та SIM-карту. Якщо заливати з європейського/українського IP, відео ніколи не потраплять в US FYP. Якщо заливати з брудного публічного проксі — ви отримаєте вічні **0 переглядів** (jail). |
| **Instagram Reels** | 🔴 **КРИТИЧНО** | Meta відстежує раптові зміни гео. Якщо акаунт, орієнтований на US, оновлюється з іншої країни, Meta активує чекпоінти або знижує рейтинг акаунта в рекомендаціях. |
| **Facebook Reels** | 🔴 **КРИТИЧНО** | Спільний з Instagram штучний інтелект виявлення фроду Meta. |
| **Snapchat Spotlight** | 🔴 **КРИТИЧНО** | Spotlight монетизація та стрічка жорстко гео-огороджені (geo-fenced) для американських користувачів. |
| **Threads** | 🔴 **КРИТИЧНО** | Безпосередньо прив'язаний до Meta trust-score вашого профілю Instagram. |
| **YouTube Shorts** | 🟢 **НЕ ПОТРІБЕН (Direct)** | YouTube використовує офіційний Google OAuth2. Google розцінює ротаційні/чужі проксі як злам («Підозрілий вхід») і скидає авторизацію. Алгоритм Shorts базується на retention/CTR, а не IP заливу. |
| **Bluesky** | 🟢 **НЕ ПОТРІБЕН (Direct)** | Децентралізований відкритий AT Protocol. Працює напряму. |
| **Telegram Канал** | 🟢 **НЕ ПОТРІБЕН (Direct)** | Офіційний Bot API працює напряму. |
| **Pinterest** | 🟢 **НЕ ПОТРІБЕН (Direct)** | Офіційний API не застосовує гео-блокування. |
| **X (Twitter)** | 🟢 **НЕ ПОТРІБЕН (Direct)** | Офіційний API v2 працює стабільно напряму. |

---

## 🚀 2. Варіант 1: Webshare.io (Найпростіший, 0 грн, без картки)

Webshare надає **10 безкоштовних приватних проксі назавжди** з підтримкою SOCKS5 та HTTP.

1. Зареєструйтесь на [Webshare.io](https://www.webshare.io/) (електронна пошта, банківська карта **не потрібна**).
2. Перейдіть у розділ **Proxy** -> **Settings**.
3. У виборі країн виберіть **United States (US)**.
4. Оберіть протокол **SOCKS5**.
5. Скопіюйте IP, Port, Username та Password.
6. Вставте у ваш `.env`:
   ```bash
   US_NY_PROXY_URL=socks5://username:password@ip:port
   STRICT_PROXY_CHECK=true
   ```
> [!NOTE]
> Бот автоматично транслює `socks5://` у `socks5h://` для запобігання DNS-витоку (DNS Leak). DNS-запити резолвляться в США.

---

## 🛡 3. Варіант 2: Власний приватний SOCKS5 у New York (Fly.io Free Tier)

Fly.io надає до 3 віртуальних машин `shared-cpu-1x` (256MB) **повністю безкоштовно**.  
Регіон **`ewr`** (Secaucus / Newark) знаходиться в метрополії Нью-Йорка (New York Metro).

### Кроки налаштування (займає 3 хвилини):

1. Встановіть `flyctl`:
   ```bash
   # macOS:
   brew install flyctl
   ```
2. Увійдіть у свій акаунт:
   ```bash
   fly auth signup  # або fly auth login
   ```
3. Створіть окрему папку та запустіть надлегкий `microsocks`:
   ```bash
   mkdir -p ~/fly-ny-proxy && cd ~/fly-ny-proxy
   ```
4. Створіть `Dockerfile`:
   ```dockerfile
   FROM alpine:latest
   RUN apk add --no-cache microsocks
   EXPOSE 1080
   CMD ["microsocks", "-1", "-p", "1080", "-u", "admin", "-P", "SuperSecret123Pass"]
   ```
5. Створіть `fly.toml`:
   ```toml
   app = "my-private-ny-proxy"
   primary_region = "ewr"

   [build]

   [[services]]
     internal_port = 1080
     protocol = "tcp"

     [[services.ports]]
       port = 1080
   ```
6. Розгорніть безкоштовний проксі:
   ```bash
   fly launch --region ewr --now
   ```
7. Отримайте IP-адресу вашого контейнера (`fly ips list`) і пропишіть у `.env`:
   ```bash
   US_NY_PROXY_URL=socks5://admin:SuperSecret123Pass@YOUR_FLY_IP:1080
   STRICT_PROXY_CHECK=true
   ```

**Переваги власного Fly.io:**
- 100% приватна IP-адреса, яка належить тільки вам.
- Жодних сусідів по IP, які могли б зіпсувати репутацію акаунта.
- Швидкість гігабітного каналу біля самого Мангеттена.

---

## ⚡️ 4. Варіант 3: Cloudflare WARP (Zero-Cost)

Якщо у вас встановлений безкоштовний клієнт Cloudflare WARP:
1. Переведіть режим у Proxy Mode:
   ```bash
   warp-cli mode proxy
   warp-cli set-proxy-port 40000
   warp-cli connect
   ```
2. Пропишіть у `.env`:
   ```bash
   US_NY_PROXY_URL=socks5://127.0.0.1:40000
   ```

---

## 🔍 5. Як перевірити статус проксі у Telegram-боті?

1. Відкрийте Telegram-бота.
2. Натисніть **🌐 Перевірити US/NY Проксі** або надішліть команду `/proxy`.
3. Бот у режимі реального часу відправить запит через проксі та покаже:
   - Зовнішній IP
   - Країну (United States)
   - Місто (New York)
   - Провайдера (ISP)
4. Якщо проксі не активний, перемикач `STRICT_PROXY_CHECK=true` автоматично заблокує залив у TikTok, Reels, Snapchat та Threads, щоб уникнути тіньового бану, і дозволить опублікувати тільки в YouTube Shorts, Bluesky та Telegram.
