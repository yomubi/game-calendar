FROM denoland/deno:alpine-2.1.4
WORKDIR /app
COPY main.ts .
ENV PORT=8000
EXPOSE 8000
CMD ["run", "--allow-net", "--allow-env", "main.ts"]
