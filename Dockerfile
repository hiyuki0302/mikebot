FROM python:3.12.5-slim

# タイムゾーンと文字コード
ENV TZ=Asia/Tokyo \
    LANG=C.UTF-8 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 必要なパッケージだけ入れる（git不要になったのでapt-get不要）
WORKDIR /app

# requirementsだけ先に入れてキャッシュ利用
COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# 残りのソースコードをコピー
COPY . .

# （ここでAPIキーやconfigは絶対イメージに含めない）

# 任意: 非rootで実行したい場合
# RUN useradd -m trader && chown -R trader /app
# USER trader

# デフォルトコマンド（変更OK）
CMD ["python", "entry.py"]

