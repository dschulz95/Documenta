# Linux test runner for the host scripts (backup.sh, restore.sh).
# Gives the tests the same tools as the Raspberry Pi: bash, rsync, mountpoint, docker compose.
# It talks to the running stack through the mounted Docker socket.
FROM docker:29.9.3-cli
RUN apk add --no-cache bash rsync util-linux-misc coreutils
WORKDIR /work/documents
CMD ["sleep", "infinity"]
