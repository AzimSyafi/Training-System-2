// quiz_builder.js
// Pure JavaScript Quiz Builder UI for Upload Content (no React)

console.log('quiz_builder.js loaded (vanilla JS)');

function createQuizBuilder(root) {
  root.innerHTML = '';
  let quizData = [];

  // Helper to load quiz data for a module
  async function loadQuizData(moduleId) {
    if (!moduleId) return;
    try {
      const res = await fetch(`/api/load_quiz/${moduleId}`);
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data) && data.length > 0) {
          quizData = data;
        } else {
          quizData = [{ text: '', answers: [ { text: '', isCorrect: true }, { text: '', isCorrect: false } ] }];
        }
      } else {
        quizData = [{ text: '', answers: [ { text: '', isCorrect: true }, { text: '', isCorrect: false } ] }];
      }
    } catch {
      quizData = [{ text: '', answers: [ { text: '', isCorrect: true }, { text: '', isCorrect: false } ] }];
    }
    render();
  }

  function render() {
    root.innerHTML = '';
    quizData.forEach((q, qIdx) => {
      const card = document.createElement('div');
      card.className = 'bg-white border-2 border-gray-200 rounded-lg shadow p-4 mb-6 relative';
      card.innerHTML = `
        <div class="flex items-center mb-2">
          <span class="font-semibold text-lg mr-2">Question ${qIdx + 1}:</span>
          <input type="text" class="flex-1 border rounded px-2 py-1 focus:outline-none" placeholder="Enter your question..." value="${q.text}" maxlength="200" data-qidx="${qIdx}" />
          <span class="ml-2 text-xs text-gray-500">${q.text.length}/200</span>
        </div>
        <div class="ml-6" id="answers-${qIdx}"></div>
        <button type="button" class="mt-2 px-3 py-1 bg-blue-100 text-blue-700 rounded" id="add-answer-${qIdx}" ${q.answers.length >= 3 ? 'disabled' : ''}>+ Add Answer (${q.answers.length}/3)</button>
        <div class="flex justify-between mt-4">
          <button type="button" class="text-red-500 hover:text-red-700 text-sm" id="delete-q-${qIdx}" ${quizData.length === 1 ? 'disabled' : ''}>Delete Question</button>
        </div>
      `;
      root.appendChild(card);
      // Question text event
      const questionInput = card.querySelector('input[type="text"]');
      questionInput.addEventListener('input', e => {
        q.text = e.target.value.slice(0, 200);
        // Do not re-render here
        card.querySelector('.ml-2.text-xs.text-gray-500').textContent = `${q.text.length}/200`;
      });
      // Answers
      const answersDiv = card.querySelector(`#answers-${qIdx}`);
      q.answers.forEach((a, aIdx) => {
        const ansDiv = document.createElement('div');
        ansDiv.className = `flex items-center gap-2 mb-2 ${a.isCorrect ? 'bg-green-50 border-green-400' : 'bg-white'} border rounded p-2`;
        ansDiv.innerHTML = `
          <input type="radio" name="correct-${qIdx}" ${a.isCorrect ? 'checked' : ''} />
          <input type="text" class="flex-1 border rounded px-2 py-1 focus:outline-none" placeholder="Answer text..." value="${a.text}" maxlength="100" />
          ${q.answers.length > 2 ? `<button type="button" class="text-red-500 hover:text-red-700 px-2">&times;</button>` : ''}
        `;
        // Correct answer radio
        ansDiv.querySelector('input[type="radio"]').addEventListener('change', () => {
          q.answers.forEach((ans, idx) => ans.isCorrect = idx === aIdx);
          render();
        });
        // Answer text
        const answerInput = ansDiv.querySelector('input[type="text"]');
        answerInput.addEventListener('input', e => {
          a.text = e.target.value.slice(0, 100);
          // Do not re-render here
        });
        // Remove answer
        if (q.answers.length > 2) {
          ansDiv.querySelector('button').addEventListener('click', () => {
            q.answers.splice(aIdx, 1);
            if (!q.answers.some(ans => ans.isCorrect)) q.answers[0].isCorrect = true;
            render();
          });
        }
        answersDiv.appendChild(ansDiv);
      });
      // Add answer
      card.querySelector(`#add-answer-${qIdx}`).addEventListener('click', () => {
        if (q.answers.length < 3) {
          q.answers.push({ text: '', isCorrect: false });
          render();
          autoSave();
        }
      });
      // Delete question
      card.querySelector(`#delete-q-${qIdx}`).addEventListener('click', () => {
        if (quizData.length > 1) {
          quizData.splice(qIdx, 1);
          render();
          autoSave();
        }
      });
    });
    // Add new question button
    const addQBtn = document.createElement('button');
    addQBtn.type = 'button';
    addQBtn.className = 'mb-4 px-4 py-2 bg-gray-100 text-gray-700 rounded hover:bg-gray-200';
    addQBtn.textContent = '+ Add New Question';
    addQBtn.addEventListener('click', () => {
      quizData.push({ text: '', answers: [ { text: '', isCorrect: true }, { text: '', isCorrect: false } ] });
      render();
      autoSave();
    });
    root.appendChild(addQBtn);

    // Add clear button
    const clearBtn = document.createElement('button');
    clearBtn.type = 'button';
    clearBtn.className = 'mb-4 ml-2 px-4 py-2 bg-red-100 text-red-700 rounded hover:bg-red-200';
    clearBtn.textContent = 'Clear Quiz';
    clearBtn.addEventListener('click', () => {
      if (confirm('Are you sure you want to clear the entire quiz?')) {
        quizData = [];
        render();
        autoSave();
      }
    });
    root.appendChild(clearBtn);

    // Removed Save/Cancel buttons
    // Hidden input for form submission (if needed for legacy)
    if (!document.getElementById('quiz-data-input')) {
      const hidden = document.createElement('input');
      hidden.type = 'hidden';
      hidden.id = 'quiz-data-input';
      hidden.name = 'quiz_data';
      document.getElementById('contentForm').appendChild(hidden);
    }
  }

  // Auto-save logic
  function autoSave() {
    const moduleId = document.getElementById('moduleSelect')?.value;
    if (!moduleId) return;
    fetch('/api/save_quiz', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ module_id: moduleId, quiz: quizData })
    })
    .then(res => res.json())
    .then(data => {
      // Optionally show a saved indicator
      // console.log('Quiz saved', data);
    });
  }

  // Initial state
  const moduleId = document.getElementById('moduleSelect')?.value;
  if (moduleId) {
    loadQuizData(moduleId);
  } else {
    quizData.push({ text: '', answers: [ { text: '', isCorrect: true }, { text: '', isCorrect: false } ] });
    render();
  }

  // Watch for changes to auto-save
  root.addEventListener('input', autoSave);
}

function mountQuizBuilderVanilla() {
  const root = document.getElementById('quiz-builder-root');
  if (root) createQuizBuilder(root);
}
function unmountQuizBuilderVanilla() {
  const root = document.getElementById('quiz-builder-root');
  if (root) root.innerHTML = '';
}

// Listen for module change to reload quiz
window.addEventListener('DOMContentLoaded', function() {
  const select = document.getElementById('contentTypeSelect');
  const moduleSelect = document.getElementById('moduleSelect');
  if (!select) return;
  function handleChange() {
    if (select.value === 'quiz') {
      mountQuizBuilderVanilla();
    } else {
      unmountQuizBuilderVanilla();
    }
  }
  select.addEventListener('change', handleChange);
  if (moduleSelect) {
    moduleSelect.addEventListener('change', function() {
      if (select.value === 'quiz') {
        mountQuizBuilderVanilla();
      }
    });
  }
  if (select.value === 'quiz') mountQuizBuilderVanilla();
});
