document.addEventListener('DOMContentLoaded', function() {
    const chatbotToggle = document.querySelector('.chatbot-toggle');
    const chatbotWidget = document.querySelector('.chatbot-widget');
    const closeChatbot = document.querySelector('.close-chatbot');
    const chatInput = document.getElementById('chatInput');
    const sendMessageBtn = document.getElementById('sendMessage');
    const chatMessages = document.querySelector('.chat-messages');
    
    // Toggle chatbot visibility
    chatbotToggle.addEventListener('click', function() {
        chatbotWidget.classList.toggle('active');
        if (chatbotWidget.classList.contains('active')) {
            loadChatHistory();
        }
    });
    
    closeChatbot.addEventListener('click', function() {
        chatbotWidget.classList.remove('active');
    });
    
    // Send message on button click or Enter key
    sendMessageBtn.addEventListener('click', sendMessage);
    chatInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            sendMessage();
        }
    });
    
    function sendMessage() {
        const message = chatInput.value.trim();
        if (message) {
            // Add user message to chat
            addMessage(message, 'user');
            chatInput.value = '';
            
            // Send to server and get response
            fetch('/chatbot', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ message: message }),
            })
            .then(response => response.json())
            .then(data => {
                addMessage(data.response, 'bot');
            })
            .catch(error => {
                console.error('Error:', error);
                addMessage("Sorry, I'm having trouble connecting. Please try again later.", 'bot');
            });
        }
    }
    
    function addMessage(text, sender) {
        const messageDiv = document.createElement('div');
        messageDiv.classList.add(`${sender}-message`);
        
        const messagePara = document.createElement('p');
        messagePara.textContent = text;
        messageDiv.appendChild(messagePara);
        
        chatMessages.appendChild(messageDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }
    
    function loadChatHistory() {
        fetch('/chat_history')
        .then(response => response.json())
        .then(history => {
            // Clear existing messages except the initial bot message
            const initialMessage = chatMessages.querySelector('.bot-message');
            chatMessages.innerHTML = '';
            if (initialMessage) {
                chatMessages.appendChild(initialMessage);
            }
            
            // Add history messages
            history.forEach(item => {
                addMessage(item.user_message, 'user');
                addMessage(item.bot_response, 'bot');
            });
        })
        .catch(error => {
            console.error('Error loading chat history:', error);
        });
    }
});
const chatMessages = document.getElementById('chat-messages');
const chatInputBox = document.getElementById('chat-input-box');
const chatSendBtn = document.getElementById('chat-send-btn');

let predictionStep = 0;
let predictionData = {};

function appendMessage(message, sender='bot') {
    const msgDiv = document.createElement('div');
    msgDiv.className = sender === 'bot' ? 'bot-message' : 'user-message';
    msgDiv.innerText = message;
    chatMessages.appendChild(msgDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function resetPrediction() {
    predictionStep = 0;
    predictionData = {};
}

chatSendBtn.onclick = async function() {
    const userMsg = chatInputBox.value.trim();
    if (!userMsg) return;
    appendMessage(userMsg, 'user');
    chatInputBox.value = '';

    // Prediction flow
    if (predictionStep > 0) {
        // Collecting answers
        const steps = ['interest', 'education', 'skill', 'qualification'];
        predictionData[steps[predictionStep - 1]] = userMsg;
        predictionStep++;
        if (predictionStep <= steps.length) {
            appendMessage(`Please enter your ${steps[predictionStep-1]}:`);
        } else {
            // Send to backend
            appendMessage("Predicting best course for you...");
            const res = await fetch('/predict_course', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(predictionData)
            });
            const data = await res.json();
            appendMessage(`Recommended Course: ${data.predicted_course}`);
            resetPrediction();
        }
        return;
    }

    // Start prediction if user requests it
    if (/recommend.*course|suggest.*course|best course/i.test(userMsg)) {
        predictionStep = 1;
        appendMessage("Sure! Let's find the best course for you. Please enter your interest (e.g. Programming, Design, etc.):");
        return;
    }

    // [Your normal chatbot logic here...]
    appendMessage("I'm here to help! Ask me for course recommendations if you'd like.");
};