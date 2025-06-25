document.addEventListener("DOMContentLoaded", function () {
    const chatBtn = document.getElementById('chat-btn');
    const chatInput = document.getElementById('chat-input');
    const chatBox = document.getElementById('chat-box');

    if (chatBtn && chatInput && chatBox) {
        chatBtn.addEventListener('click', () => {
            const msg = chatInput.value.trim();
            if (!msg) return;

            fetch('/chat', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ message: msg })
            })
            .then(res => res.json())
            .then(data => {
                chatBox.innerHTML += `<div><b>You:</b> ${msg}</div>`;
                chatBox.innerHTML += `<div><b>Assistant:</b> ${data.reply || data.error}</div>`;
                chatBox.scrollTop = chatBox.scrollHeight;
                chatInput.value = '';
            });
        });
    }
});
