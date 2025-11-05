# Asystent Gry Dune: Imperium (Dune: Imperium Game Assistant)

## Opis Projektu

**Asystent Gry Dune: Imperium** to aplikacja webowa (oparta na Flask), która służy jako cyfrowy pomocnik do zarządzania fizyczną grą planszową *Dune: Imperium*.

Nie jest to pełna, automatyczna implementacja gry. Jest to narzędzie stworzone, aby ułatwić graczom śledzenie złożonego stanu gry, automatyzować niektóre obliczenia i wspierać rozgrywkę z udziałem "gracza AI" poprzez generowanie dla niego specjalnych promptów.

Głównym celem aplikacji jest:
1.  Utrzymywanie "źródła prawdy" (Source of Truth) o stanie gry (zasoby, karty, lokacje).
2.  Walidacja i logowanie ruchów graczy w Fazie Agentów.
3.  Automatyczne obliczanie statystyk (Perswazja, Siła) na potrzeby Fazy Odkrycia.
4.  Generowanie ustrukturyzowanych promptów tekstowych, które można przekazać do zewnętrznego modelu LLM (jak ChatGPT, Gemini, Claude), aby uzyskać sugestię ruchu dla gracza AI.

## Kluczowe Funkcje

* **Zarządzanie Stanem Gry:** Śledzi rundę, fazę, zasoby graczy (Solari, Woda, Przyprawa, Wojsko), wpływy oraz stan lokacji (kto zajął).
* **Interfejs Fazy Agentów:** Pozwala graczom na wybranie karty z ręki (lub talii dla ludzi) i lokacji docelowej. Aplikacja sprawdza poprawność ruchu (np. czy lokacja jest wolna, czy karta ma odpowiedni symbol, czy gracza stać na koszt).
* **Logowanie Historii:** Każdy ruch, pas, zagranie intrygi czy ustawienie konfliktu jest logowane w historii rundy.
* **Interfejs Fazy Odkrycia:** Po zakończeniu Fazy Agentów, aplikacja automatycznie przechodzi do widoku `/reveal`.
    * Automatycznie oblicza i wyświetla sumę Perswazji i Siły dla wszystkich graczy na podstawie ich zagranych kart i kart na ręce.
    * Umożliwia ręczne zalogowanie wyników konfliktu (kto zajął które miejsce).
    * Pozwala na rejestrowanie zakupów z Rzędu Imperium, walidując koszt i dostępną Perswazję.
* **Generator Promptów AI:** Dedykowana strona (`/ai_prompt`) generuje szczegółowy prompt dla gracza AI (`Peter`). Prompt zawiera:
    * Aktualny stan gry, nagrody w konflikcie, historię ruchów.
    * Podsumowanie publicznych informacji o przeciwnikach.
    * Pełny, ukryty stan gracza AI (ręka, zasoby, intrygi) w formacie JSON, gotowy do analizy przez model językowy.
* **Zarządzanie Grą:**
    * Ręczne ustawianie ręki gracza AI (na wypadek, gdyby automatyczne dociąganie nie było pożądane).
    * Rozpoczęcie nowej rundy (czyści planszę, przesuwa karty, automatycznie dociąga 5 kart dla wszystkich graczy).
    * Pełny reset gry do stanu domyślnego (`game_stat.DEFAULT.json`).

## Technologie

* **Backend:** Python, Flask
* **Frontend:** HTML5, CSS, JavaScript (po stronie klienta)
* **Przechowywanie Danych:** Pliki JSON (dla stanu gry, definicji kart, lokacji i intryg)

## Instalacja i Uruchomienie

1.  Upewnij się, że masz zainstalowanego Pythona.
2.  Zainstaluj wymagane pakiety (tylko Flask):
    ```bash
    pip install -r requirements.txt
    ```
   
3.  Uruchom aplikację:
    ```bash
    python app/app.py
    ```
   
4.  Otwórz przeglądarkę i przejdź pod adres `http://127.0.0.1:5000` (lub adres IP serwera, jeśli uruchamiasz na innym urządzeniu).

## Jak Używać

1.  **Start Rundy:** Na początku rundy wejdź na stronę główną. W panelu "Set Conflict" wprowadź nazwę karty konfliktu i nagrody, a następnie kliknij "Set/Update Conflict".
2.  **Ruch Gracza (Człowiek):**
    * W panelu "Agent Movement" wybierz gracza, kartę z jego talii (dla ludzi widoczna jest cała talia, `deck_pool`) oraz dostępną lokację.
    * Kliknij "Save Agent Move". Aplikacja przetworzy ruch, zaktualizuje zasoby i doda wpis do historii.
3.  **Ruch Gracza (AI):**
    * Gdy przychodzi tura gracza AI (domyślnie "Peter"), kliknij przycisk "Generate AI Prompt".
    * Otworzy się nowa karta z promptem. Skopiuj cały tekst.
    * Wklej skopiowany prompt do zewnętrznego modelu LLM (np. ChatGPT, Gemini) i poproś o decyzję (np. "Jaki jest twój ruch? Podaj ID karty i ID lokacji.").
    * Wróć do aplikacji, wybierz "Peter" z listy graczy, a następnie wybierz kartę i lokację wskazane przez AI.
    * Kliknij "Save Agent Move", aby wykonać ruch za AI.
4.  **Faza Odkrycia (Reveal):**
    * Gdy wszyscy gracze spasują lub wyślą agentów, aplikacja automatycznie przejdzie do fazy "REVEAL" i przekieruje Cię na stronę `/reveal`.
    * Na stronie Fazy Odkrycia zobaczysz podsumowanie siły i perswazji.
    * Porównaj siłę i ręcznie wprowadź zwycięzców w panelu "Resolve Conflict".
    * Rejestruj zakupy kart dla każdego gracza za pomocą panelu "Market (Imperium Row)".
5.  **Nowa Runda:**
    * Po zakończeniu Fazy Odkrycia, kliknij przycisk "Start New Round (Cleanup)".
    * Aplikacja automatycznie wyczyści planszę, zresetuje agentów, przetasuje talie i dobierze 5 kart każdemu graczowi, rozpoczynając nową rundę w Fazie Agentów.
