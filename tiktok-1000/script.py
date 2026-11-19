"""Сценарий ролика «Как заработать первые $1000».

Каждая реплика: speaker (max / liza / nar), tts — текст для синтеза речи,
cap — текст субтитров, emo/pose — эмоция и поза говорящего,
other — эмоция второго героя, fx — события относительно начала реплики.
"""

VOICES = {
    "nar": dict(voice="aleksandr-hq", rate=112, pitch=100),
    "max": dict(voice="artemiy", rate=110, pitch=104),
    "liza": dict(voice="anna", rate=108, pitch=102),
}

SCENES = [
    dict(id="hook", step=None, title="ПЕРВЫЕ $1000", sub="без казино и схем",
         bg=((255, 94, 98), (255, 153, 102))),
    dict(id="skill", step="ШАГ 1", title="ПРОДАЙ НАВЫК", sub="то, что умеешь лучше друзей",
         bg=((67, 97, 238), (114, 9, 183))),
    dict(id="sell", step="ШАГ 2", title="ПРОДАЙ НЕНУЖНОЕ", sub="деньги пылятся на полке",
         bg=((0, 150, 136), (38, 70, 83))),
    dict(id="local", step="ШАГ 3", title="ДЕНЬГИ РЯДОМ", sub="помогай людям вокруг",
         bg=((247, 127, 0), (214, 40, 40))),
    dict(id="twist", step="ЛОВУШКА", title="НЕ ТРАТЬ ВСЁ!", sub="деньги должны работать",
         bg=((131, 56, 236), (58, 12, 163))),
    dict(id="final", step=None, title="$1000 ЕСТЬ!", sub="а теперь — вторая",
         bg=((255, 190, 11), (251, 86, 7))),
]

LINES = [
    # ---------- HOOK ----------
    dict(scene="hook", speaker="max", emo="shock", pose="shrug", other="normal",
         tts="На карте... три доллара. А мне нужна тысяча!",
         cap="На карте... 3$. А мне нужна ТЫСЯЧА! 😱",
         fx=[(0.0, "props", ["💳", "😱", "💸"])]),
    dict(scene="hook", speaker="liza", emo="smirk", pose="point", other="sad",
         tts="Спокойно. Без казино, крипты и курсов за девятьсот девяносто девять.",
         cap="Спокойно. Без казино, крипты и курсов за 999$ 😏",
         fx=[(0.3, "props", ["🎰", "❌", "📉"])]),
    dict(scene="hook", speaker="nar", emo="normal", pose="idle", other="normal",
         tts="Три шага. Один месяц. Поехали!",
         cap="3 шага. 1 месяц. Поехали! 🚀",
         fx=[(0.0, "props", ["1️⃣", "2️⃣", "3️⃣"]), (1.6, "jump", "both")]),

    # ---------- ШАГ 1 ----------
    dict(scene="skill", speaker="liza", emo="normal", pose="think", other="think",
         tts="Что ты умеешь делать лучше друзей?",
         cap="Что ты умеешь делать лучше друзей? 🤔",
         fx=[(0.0, "props", ["🎨", "🎬", "📸"])]),
    dict(scene="skill", speaker="max", emo="normal", pose="shrug", other="normal",
         tts="Ну... монтирую видосы. Для себя.",
         cap="Ну... монтирую видосы. Для себя 🎬"),
    dict(scene="skill", speaker="liza", emo="happy", pose="point", other="shock",
         tts="Это уже услуга! Пять роликов для местных кафе по сорок долларов.",
         cap="Это уже УСЛУГА! 5 роликов для местных кафе по 40$ ☕",
         fx=[(0.2, "props", ["☕", "🎬", "💵"]), (-0.3, "money", 200)]),
    dict(scene="skill", speaker="max", emo="happy", pose="cheer", other="happy",
         tts="Двести долларов! За то, что я и так люблю?!",
         cap="200$! За то, что я и так люблю?! 🤩",
         fx=[(0.0, "jump", "max")]),

    # ---------- ШАГ 2 ----------
    dict(scene="sell", speaker="nar", emo="normal", pose="idle", other="normal",
         tts="Шаг второй. Оглянись: деньги пылятся на полке.",
         cap="Шаг 2. Оглянись: деньги пылятся на полке 👀",
         fx=[(0.0, "props", ["🎮", "🎧", "🧥"])]),
    dict(scene="sell", speaker="max", emo="think", pose="think", other="normal",
         tts="Старая приставка, наушники, куртка...",
         cap="Старая приставка, наушники, куртка... 🤨",
         fx=[(0.0, "tags", ["+80$", "+30$", "+40$"])]),
    dict(scene="sell", speaker="liza", emo="happy", pose="point", other="happy",
         tts="Фото при дневном свете, честное описание, и плюс сто пятьдесят.",
         cap="Фото при дневном свете + честное описание = +150$ 📦",
         fx=[(-0.3, "money", 150)]),

    # ---------- ШАГ 3 ----------
    dict(scene="local", speaker="nar", emo="normal", pose="idle", other="normal",
         tts="Шаг третий. Помогай людям рядом.",
         cap="Шаг 3. Помогай людям рядом 🏡",
         fx=[(0.0, "props", ["📚", "💻", "🐕"])]),
    dict(scene="local", speaker="liza", emo="normal", pose="wave", other="think",
         tts="Репетиторство, помощь соседям с компьютером, выгул собак.",
         cap="Репетиторство, помощь соседям с компом, выгул собак 🐶"),
    dict(scene="local", speaker="max", emo="happy", pose="point", other="happy",
         tts="Четыре ученика по пятнадцать долларов в неделю. Это двести сорок за месяц!",
         cap="4 ученика × 15$ в неделю = 240$ за месяц! 📈",
         fx=[(-0.4, "money", 240)]),

    # ---------- ПОВОРОТ ----------
    dict(scene="twist", speaker="max", emo="happy", pose="cheer", other="shock",
         tts="Всё, я богач! Иду за кроссовками!",
         cap="Всё, я БОГАЧ! Иду за кроссовками! 👟✨",
         fx=[(0.0, "sneaker", None), (0.0, "jump", "max")]),
    dict(scene="twist", speaker="liza", emo="angry", pose="stop", other="shock",
         tts="Стоп! Это ловушка. Вложи деньги в себя.",
         cap="СТОП! 🛑 Это ловушка. Вложи деньги в себя.",
         fx=[(0.0, "stop", None)]),
    dict(scene="twist", speaker="nar", emo="normal", pose="idle", other="normal",
         tts="Макс купил микрофон и поднял цену до семидесяти долларов за ролик.",
         cap="Макс купил микрофон 🎤 и поднял цену до 70$ за ролик",
         fx=[(0.0, "props", ["🎤", "⬆️", "💼"])]),
    dict(scene="twist", speaker="liza", emo="smirk", pose="point", other="happy",
         tts="Шесть заказов, и...",
         cap="6 заказов, и...",
         fx=[(-0.2, "money", 420)]),

    # ---------- ФИНАЛ ----------
    dict(scene="final", speaker="max", emo="happy", pose="cheer", other="happy",
         tts="Тысяча долларов! Я сделал это!",
         cap="1000$! Я СДЕЛАЛ ЭТО! 🏆",
         fx=[(0.0, "confetti", None), (0.0, "jump", "both"), (0.0, "props", ["🏆", "🎉", "💰"])]),
    dict(scene="final", speaker="liza", emo="smirk", pose="wave", other="shock",
         tts="Нет, Макс. Ты сделал систему. Вторая тысяча будет быстрее.",
         cap="Нет, Макс. Ты сделал СИСТЕМУ. Вторая тысяча будет быстрее 😉"),
    dict(scene="final", speaker="nar", emo="normal", pose="idle", other="happy",
         tts="Первая тысяча — это не удача, а план. Сохрани видео и начни сегодня!",
         cap="Первая $1000 — это не удача, а ПЛАН. Сохрани и начни сегодня! 🔥"),
]

START_MONEY = 3
GOAL = 1000
