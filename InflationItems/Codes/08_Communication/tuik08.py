"""TÜİK CPI division 08 (Information and communication) item codes for the 08 scrapers.

Every 08_Communication CSV starts with the same four columns (``COLUMNS``):

    product_name, price, category_number, sub_category_number

``category_number`` is always 8. ``sub_category_number`` is the 7-digit TÜİK item code from
"CPI methodological notes", Appendix 1 (basket of goods and services): e.g. ``0812002`` Mobile
phone. A product sold on an 08 website that matches none of the 08 items (game consoles,
small home appliances, software licences, ...) gets ``"0"``.

``classify(name, hint)`` decides from the product name first and falls back to ``hint`` (the
site's own category / category URL) when the name says nothing. Rules are ordered: products
outside 08 first, then accessories (so "iPhone 17 kılıfı" is not a phone), then devices.
"""

import re

CATEGORY_NUMBER = 8
COLUMNS = ["product_name", "price", "category_number", "sub_category_number"]

MOBILE_PHONE = "0812002"            # Mobile phone
COMPUTER = "0813101"                # Computer (computers, laptops and tablets)
PERIPHERALS = "0813209"             # Computer peripherals (and their consumables)
AUDIO_VIDEO = "0814001"             # Audio-video equipment
TELEVISION = "0814007"              # Television
OTHER_DEVICES = "0819103"           # Other communication devices (smart watches, bands, ...)
ACCESSORIES = "0819201"             # Info-communication accessories
MOBILE_SERVICE = "0832001"          # Mobile phone service fee
INTERNET_SERVICE = "0833001"        # Internet service fee
REPAIR = "0835001"                  # Repair and maintenance of information and communication equipment
DIGITAL_CONTENT = "0839201"         # Digital content platform subscription
NOT_IN_BASKET = "0"

_ASCII = str.maketrans("ıİşŞğĞüÜöÖçÇâÂîÎûÛ", "iissgguuooccaaiiuu")


def _norm(text):
    """Lowercase, Turkish letters to ASCII, punctuation/URL separators to spaces."""
    text = (text or "").replace("İ", "i").replace("I", "ı").lower().translate(_ASCII)
    return " " + re.sub(r"[^a-z0-9+]+", " ", text).strip() + " "


# (code, regex on the normalized text). First match wins.
# ponytail: keyword rules, a few hundred products per day land in the wrong item; use the
# site's own taxonomy (see Samsung/Huawei) wherever a scraper has one.
_LAPTOP_LINES = (r"ideapad|thinkpad|thinkbook|legion|loq|yoga|vivobook|zenbook|expertbook|tuf gaming|rog strix g|rog zephyrus"
                 r"|omen|victus|pavilion|elitebook|probook|inspiron|latitude|vostro|xps|aspire|nitro|predator|swift"
                 r"|galaxy book|surface (pro|laptop)|matebook|magicbook|monster (abra|tulpar|semruk)")
_RULES = [
    (NOT_IN_BASKET, r" (oyun )?konsol| playstation| ps[45] | xbox| nintendo| oyun kolu| gamepad| joystick| direksiyon"
                    r"| flight stick| hotas| oyuncu (koltu|masa)| vr (gozlu|baslik)| meta quest| sanal gerceklik| oyunlar? "
                    r"| drone| dron | supurge| utu | kahve makine| turk kahve| espresso| cay makine| kettle| blender| mikser"
                    r"| pencilwash| dogray| tost| ekmek kizart| airfryer| fritoz| firin| mikrodalga| mutfak robot| sebze sikac"
                    r"| buzdolab| dondurucu| sarap dolab| camasir| bulasik| klima| isitici| vantilator| (masaustu|ayakli|tavan|sarjli|boyun) (mini )?(sarjli )?fan| hava sogutucu"
                    r"| hava temizle| nem alma| sac | sac kurut| sac sekil| fon makine| airwrap| tiras| epilat| ipl | masaj"
                    r"| dis fircas| agiz dusu| tarti | cilt bakim| scooter| kaykay| elektrikli arac| valiz| bavul| yazilim"
                    r"| lisans| kargo bedeli| hizmet paketi| garanti paketi| odeme jeton| hesap makine| etiket makine"
                    r"| laminasyon| para sayma| dikis makine"),
    # "Apple Watch ... Alüminyum Kasa (ve) Spor Kordon" / "... Aluminium Case with ... Band" is the watch itself
    (OTHER_DEVICES, r"^(?!.* (uyumlu|koruyucu|kilif) ).* watch .* (kasa|case) "),
    (PERIPHERALS, r" akilli telefon yazici| magic (keyboard|trackpad|mouse)"),
    # projectors before TV: "... Android TV ... Projeksiyon Cihazı" is a projector
    (AUDIO_VIDEO, r" projeksiyon| projektor| projector"),
    (TELEVISION, r" televizyon| smart tv| (q|neo q|o|mini |micro |qned )?led tv| uhd tv| the frame| the serif| the sero"
                 r"| google tv| android tv| [0-9]{2,3} (inc|inch|ekran) .*tv "),
    (ACCESSORIES, r" kilif| kapak | case | cover| ekran koruyucu| koruyucu (cam|film)| temperli| cam koruyucu"
                  r"| sarj (cihaz|alet|adaptor|kablo|istasyon|unite|stand|dock|kutu)| powerbank| power bank"
                  r"| tasinabilir (sarj|guc)| kablo(su|lari)? | kablo seti| adaptor(u)? | donusturucu| kordon| kayis| strap"
                  r"| (notebook|laptop) sogutucu| tutucu| stand(i)? | stant | arac ici (tutucu|sarj)| arac tutucu"
                  r"| canta(si|lari)? | sirt cantasi| pencil| kalem(i)? (?!ve )| stylus| uzaktan kumanda| kumanda | remote"
                  r"| tv aski| duvar aski| aski aparat| askisi| anahtarlik| magsafe| lens(i)? | tripod| gimbal| pil | piller "
                  r"| batarya(si)? | aksesuar| accessor"),
    (AUDIO_VIDEO, r" apple tv | tv box| medya oynatici| media player| chromecast| fire tv| projeksiyon| projektor"
                  r"| projector| (studyo )?monitor kulak"),
    (MOBILE_PHONE, r" akilli telefon| cep telefon| smartphone| iphone [0-9]| iphone (air|se|e|pro) | iphone .*[0-9] ?(gb|tb) "
                   r"| galaxy [szam][0-9]| galaxy z (fold|flip)| huawei (pura|nova|mate)| redmi( note)? [0-9]| poco [a-z]?[0-9]"
                   r"| xiaomi [0-9]{2}| honor [0-9x]| reno ?[0-9]| tuslu telefon"),
    (OTHER_DEVICES, r" akilli (cocuk )?saat| smart ?watch| apple watch| galaxy watch| huawei watch| redmi watch"
                    r"| watch (fit|gt|d|ultimate|[0-9])| akilli bileklik| band [0-9]| galaxy ring| akilli yuzuk| airtag"
                    r"| smarttag| takip cihazi| telsiz| sabit telefon| dect| masaustu telefon| giyilebilir| saatler "),
    # computer models before peripherals: "MacBook Air ... 256GB SSD" is a computer
    (COMPUTER, r" laptop| dizustu| notebook| macbook| imac| mac mini| mac studio| mac pro| chromebook| aio "
               r"| (" + _LAPTOP_LINES + r") | (?<!grafik )(?<!cizim )tablet| ipad| galaxy tab| matepad| e kitap okuyucu"
               r"| kindle| kobo | (i[3579]|ryzen [3579]|r[3579]) [0-9]{4,5}[a-z]* .* ssd .* ram "),
    (PERIPHERALS, r" monitor| ekranlar | klavye| keyboard| mouse| fare | mousepad| trackpad| yazici| printer| tarayici"
                  r"| scanner| toner| kartus| murekkep| (harici|tasinabilir) (disk|ssd|hdd)| pivot| fan(i|li)? | sivi sogutma| ssd | hdd | hard disk| usb bellek"
                  r"| flash bellek| hafiza karti| micro ?sd| sd kart| ram | ekran karti| anakart| islemci| cpu "
                  r"| (bilgisayar|oyuncu|atx) .*kasa| kasa fan| sivi sogutucu| guc kaynagi| webcam| web kamera| router"
                  r"| modem| mesh| access point| menzil genislet| switch | usb hub| dock| kvm| grafik tablet| cizim tablet"
                  r"| nas | depolama| cevre birim| bilesen"),
    (AUDIO_VIDEO, r" kulaklik| headphone| headset| earbud| airpods| buds| hoparlor| speaker| soundbar| ses sistem| homepod"
                  r"| pikap| plak calar| radyo| amfi| amplifikator| receiver| mikrofon| fotograf makine| kamera"
                  r"| gopro| insta360| mp3| dvd| blu ray| ses | audio| sound"),
    (COMPUTER, r" bilgisayar| all in one| masaustu"),
]
_RULES = [(code, re.compile(pattern)) for code, pattern in _RULES]


def classify(name, hint=""):
    """Return the TÜİK item code for one product (``"0"`` when it is no 08 item)."""
    for text in (_norm(name), _norm(hint)):
        for code, rule in _RULES:
            if rule.search(text):
                return code
    return NOT_IN_BASKET


def with_category(product_name, price, sub_category_number, **rest):
    """One output row as a dict in the shared column order (``COLUMNS`` + the scraper's own)."""
    return {"product_name": product_name, "price": price, "category_number": CATEGORY_NUMBER,
            "sub_category_number": sub_category_number, **rest}


if __name__ == "__main__":
    # ponytail: smallest check that the rule order holds; run: python tuik08.py
    assert classify("iPhone 17 Pro 256GB Kozmik Turuncu Akıllı Cep Telefonu") == MOBILE_PHONE
    assert classify("iPhone 17 Pro için MagSafe özellikli Şeffaf Kılıf") == ACCESSORIES
    assert classify("Apple Watch Series 11 GPS 46mm Jet Black Alüminyum Kasa ve Siyah Spor Kordon") == OTHER_DEVICES
    assert classify("46mm Siyah Spor Kordon - M/L") == ACCESSORIES
    assert classify("Sony WH-1000XM6 Kablosuz Kulaklık") == AUDIO_VIDEO
    assert classify("Samsung 65 inç QLED 4K Smart TV") == TELEVISION
    assert classify("Apple TV 4K Wi-Fi 64GB") == AUDIO_VIDEO
    assert classify("Epson EF-22B Full HD, Android TV, Projeksiyon Cihazı") == AUDIO_VIDEO
    assert classify("LG 65QNED86 65 inç 4K MiniLED Smart TV AI Sihirli Kumanda") == TELEVISION
    assert classify("MacBook Air 13 inç M4 16GB 256GB SSD") == COMPUTER
    assert classify("Logitech MX Master 3S Mouse") == PERIPHERALS
    assert classify("PlayStation 5 Slim Konsol") == NOT_IN_BASKET
    assert classify("Dyson V15 Detect Süpürge") == NOT_IN_BASKET
    assert classify("JBL Tune 520BT", "Ev Elektroniği Kulaklıklar") == AUDIO_VIDEO
    assert classify("Nespresso Vertuo", "Küçük Ev Aletleri İçecek Hazırlama") == NOT_IN_BASKET
    assert classify("Redmi Note 14 8GB", "https://www.vatanbilgisayar.com/cep-telefonu-modelleri/") == MOBILE_PHONE
    print("tuik08 ok")
