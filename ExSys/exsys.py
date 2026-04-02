import streamlit as st
import json

# Загрузка базы знаний
def load_kb():
    with open("E:\mirsud_help_bot\ExSys\knowledge_base.json", "r", encoding="utf-8") as f:
        return json.load(f)

def run_expert_system():
    st.title("🛠 Вопросы - ответы")
    st.info("Ответьте на вопросы, чтобы получить рекомендацию по устранению проблемы.")

    kb = load_kb()
    
    # Инициализация состояния сессии для отслеживания пути
    if 'current_node' not in st.session_state:
        st.session_state.current_node = 'start'
    
    node = kb.get(st.session_state.current_node)

    # Если это узел с решением (финал)
    if "solution" in node:
        st.success("### Рекомендация:")
        st.write(node["solution"])
        if st.button("Начать сначала"):
            st.session_state.current_node = 'start'
            st.rerun()
            
    # Если это узел с вопросом (выбор)
    else:
        st.write(f"### {node['question']}")
        
        # Создаем кнопки для каждого варианта ответа
        for option_text, next_node in node["options"].items():
            if st.button(option_text):
                st.session_state.current_node = next_node
                st.rerun()

    # Боковая панель с полезными ссылками
    with st.sidebar:
        st.header("Полезные контакты")
        st.write("📞 Внутренний номер: 102")
        st.write("✉️ Эл. почта: support@corp.local")

if __name__ == "__main__":
    run_expert_system()