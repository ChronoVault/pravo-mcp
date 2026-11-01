# Деплой в Yandex Serverless Containers

Free tier Yandex Cloud включает Serverless Containers (1 млн вызовов в месяц);
нужен платёжный аккаунт с привязанной картой. Актуальные лимиты:
https://yandex.cloud/ru/docs/serverless-containers/pricing

Контейнер не хранит состояние: можно держать 0 экземпляров, первый запрос после простоя
займёт несколько секунд.

## 1. Подготовка

Установите CLI и войдите: https://yandex.cloud/ru/docs/cli/quickstart

```bash
yc init
```

## 2. Реестр и образ

```bash
yc container registry create --name pravo
yc container registry configure-docker
REGISTRY_ID=$(yc container registry get pravo --format json | jq -r .id)

docker build --platform linux/amd64 -t cr.yandex/$REGISTRY_ID/pravo-mcp:1.0.0 .
docker push cr.yandex/$REGISTRY_ID/pravo-mcp:1.0.0
```

Образ должен быть `linux/amd64`, это важно при сборке на Mac с Apple Silicon.
Если Docker Hub недоступен, передайте другой базовый образ: `--build-arg BASE_IMAGE=...`.

## 3. Сервисный аккаунт для скачивания образа

```bash
FOLDER_ID=$(yc config get folder-id)
yc iam service-account create --name pravo-puller
SA_ID=$(yc iam service-account get pravo-puller --format json | jq -r .id)
yc resource-manager folder add-access-binding $FOLDER_ID \
  --role container-registry.images.puller \
  --subject serviceAccount:$SA_ID
```

## 4. Контейнер

```bash
yc serverless container create --name pravo-mcp

yc serverless container revision deploy \
  --container-name pravo-mcp \
  --image cr.yandex/$REGISTRY_ID/pravo-mcp:1.0.0 \
  --service-account-id $SA_ID \
  --cores 1 --core-fraction 20 --memory 256MB \
  --concurrency 8 --execution-timeout 60s

# публичный доступ без авторизации
yc serverless container allow-unauthenticated-invoke pravo-mcp

yc serverless container get pravo-mcp --format json | jq -r .url
```

Флаги CLI иногда меняются: если команда не проходит, сверьтесь с `yc serverless container revision deploy --help`.

## 5. Проверка и подключение

```bash
scripts/smoke.sh https://<id>.containers.yandexcloud.net/mcp
```

В Claude: **Settings → Connectors → Add custom connector**, адрес
`https://<id>.containers.yandexcloud.net/mcp`.

Обновление: соберите образ с новым тегом, `docker push`, повторите `revision deploy`.
