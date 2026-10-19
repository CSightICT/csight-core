# Overlay the running Web image to avoid deploying unrelated worktree changes.
FROM csight-web:before-login2-20260929

COPY index.html /usr/share/nginx/html/index.html
COPY assets/ /usr/share/nginx/html/assets/
