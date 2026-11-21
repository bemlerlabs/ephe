# Quality Rubric

1. Call create_qrcode for every QR request. Never describe a QR code without creating it.
2. Extract the payload precisely: full URL (including https://), Wi-Fi in the format WIFI:T:WPA;S:Name;P:Password;;, contact as vCard when requested.
3. No recognizable payload? Ask precisely instead of guessing.
4. Answer in the user's language and name the real file path.
5. Answer in the user's language. For artifacts: use the real file path from the tool result, never an invented path.
6. Ground every number/path on real tool output; no simulated output without a returned path.
