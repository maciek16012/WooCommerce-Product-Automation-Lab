# Audyt lokalnego llama.cpp — bez ingerencji w inne usługi

Sprawdzono rzeczywisty `docker inspect llama`, `docker ps`, preset modeli oraz wybrane komunikaty startowe. Nie przebudowano ani nie restartowano kontenera. Nie usunięto żadnych modeli ani wolumenów.

## Fakty

- Kontener `llama`, obraz `ghcr.io/ggml-org/llama.cpp:server-cuda`, wersja obrazu b10951.
- Brak etykiet `com.docker.compose.*`; nie jest zarządzany przez Compose tego projektu. W katalogu głównym `C:\hermes-stack` nie znaleziono pliku Compose. Nie ma wystarczających danych, by wskazać historyczny skrypt tworzący kontener; aktualna konfiguracja Docker jest źródłem prawdy.
- Entrypoint `/app/llama-server`; argumenty `--host 0.0.0.0 --port 8080 --models-preset /models/models.ini --models-max 1`.
- Bind mount `C:\hermes-stack\models` → `/models`, RW. Preset znajduje się w `C:\hermes-stack\models\models.ini`.
- Router mode, model on-demand, alias `jarvis-qwen35-9b`, wagi Qwen3VL-8B-Instruct-Q4_K_M i mmproj Q8_0.
- GPU: wszystkie dostępne urządzenia; restart `unless-stopped`; sieć `bridge`.
- Mapowanie hosta obecnie `0.0.0.0:8080` oraz `[::]:8080`. Log potwierdza `CORS=*` i brak API key.
- Sklep pozostaje na `127.0.0.1:8090`; działa też osobna usługa signal-cli. Modele i usługa AI są częścią szerszego środowiska poza repo WooCommerce.

## Rekomendacja przygotowana do osobnego wdrożenia

Przy planowanym odtworzeniu kontenera w jego właściwym projekcie zamienić publikację portu hosta na:

```yaml
ports:
  - "127.0.0.1:8080:8080"
```

W wariancie `docker run` odpowiada temu `-p 127.0.0.1:8080:8080`. Pozostawić nasłuch serwera *wewnątrz kontenera* na `0.0.0.0`: hostowe ograniczenie portu nie wymaga zmiany wewnętrznego nasłuchu. Zachować GPU, preset, model mount, argumenty routera i restart policy. To fragment konfiguracji do właściwego projektu, nie kompletny skrypt automatycznej migracji.

Zmiana publikacji portu wymaga odtworzenia kontenera; może przerwać korzystanie przez inne workflow. Dlatego zgodnie z zakresem zadania nie zastosowano jej do współdzielonej usługi. Przed zmianą należy sprawdzić jej klientów (w tym inne kontenery), zaplanować krótką przerwę i zweryfikować `/v1/models` oraz inference.

Loopback ograniczy dostęp z sieci LAN, lecz samo w sobie nie rozwiązuje ryzyka otwartego CORS dla stron w lokalnej przeglądarce. Przy osobnym porządkowaniu serwera warto ograniczyć origins lub dodać uwierzytelnianie, po sprawdzeniu klientów i obsługiwanych opcji tej wersji. Nie wyłączono ani nie osłabiono żadnych istniejących zabezpieczeń.

Provider w tym repo już teraz wymusza loopback, nie korzysta z proxy systemowych, odrzuca przekierowania i nie wysyła kluczy. Nie zmienia to szerszej ekspozycji samego współdzielonego serwera.
