proxy_http_version 1.1;
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection "upgrade";
proxy_set_header Host $host;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_buffering off;
proxy_request_buffering off;   # upload goes straight through (XHTTP / big uploads stay fast)
client_max_body_size 0;
tcp_nodelay on;
proxy_read_timeout 1h; proxy_send_timeout 1h;
proxy_socket_keepalive on;
