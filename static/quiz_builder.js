// quiz_builder.js
// Pure JavaScript Quiz Builder UI for Upload Content (no React)

console.log('quiz_builder.js loaded (vanilla JS)');

function createQuizBuilder(root) {
  root.innerHTML = '';
  let quizData = [];
  // Attach to the nearest enclosing form so we can include quiz JSON on submission
  const parentForm = root.closest('form') || document.getElementById('contentForm') || null;
  const localModuleId = root.dataset.moduleId || document.getElementById('moduleSelect')?.value || '';
  const hiddenId = 'quiz-data-input' + (localModuleId ? ('-' + localModuleId) : '');

  // Helper to load quiz data for a module
  async function loadQuizData(moduleId) {
    if (!moduleId) return;
    try {
      const res = await fetch(`/api/load_quiz/${moduleId}`);
      if (res.ok) {
        const payload = await res.json();
        // Handle multiple formats: array, {quiz: [...]}, {questions: [...]}
        let data = [];
        if (Array.isArray(payload)) {
          data = payload;
        } else if (payload && typeof payload === 'object') {
          if (Array.isArray(payload.quiz)) {
            data = payload.quiz;
          } else if (Array.isArray(payload.questions)) {
            data = payload.questions;
          }
        }

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

  let qcountInputTimer = null;

  // Helper to grow or shrink quizData to match desired count (moved out so delegated handlers can call it)
  function adjustQuestionCount(targetCount){
    targetCount = Math.max(1, Math.min(50, parseInt(targetCount,10) || 1));
    const current = quizData.length;
    if (targetCount === current) return;
    if (targetCount > current){
      for (let i=0;i<targetCount-current;i++){
        quizData.push({ text: '', answers: [ { text: '', isCorrect: true }, { text: '', isCorrect: false } ] });
      }
    } else {
      // shrink: remove from end
      quizData.splice(targetCount);
    }
    // Re-render and autosave
    render();
    autoSave();
  }

  function render() {
    root.innerHTML = '';
    // Question count control (minus / number / plus)
    const countControl = document.createElement('div');
    countControl.className = 'flex items-center gap-2 mb-4';
    countControl.innerHTML = `
      <label class="font-semibold">Number of questions:</label>
      <div class="input-group d-flex align-items-center">
        <button type="button" class="btn btn-sm btn-outline-secondary" id="qcount-decr">&minus;</button>
        <input id="qcount-input" type="number" min="1" max="50" value="${quizData.length}" class="form-control form-control-sm mx-2" style="width:80px" />
        <button type="button" class="btn btn-sm btn-outline-secondary" id="qcount-incr">+</button>
      </div>
    `;
    root.appendChild(countControl);

    // Wire up count controls - keep only DOM creation; behavior handled by delegated listeners below
    const qcountInput = countControl.querySelector('#qcount-input');
    qcountInput.value = quizData.length;

    quizData.forEach((q, qIdx) => {
      const card = document.createElement('div');
      card.className = 'bg-white border-2 border-gray-200 rounded-lg shadow p-4 mb-6 relative';
      card.innerHTML = `
        <div class="flex items-center mb-2">
          <span class="font-semibold text-lg mr-2">Question ${qIdx + 1}:</span>
          <textarea class="flex-1 border rounded px-2 py-1 focus:outline-none" placeholder="Enter your question..." data-qidx="${qIdx}" rows="4" maxlength="1000">${q.text || ''}</textarea>
          <span class="ml-2 text-xs text-gray-500">${q.text.length}/1000</span>
        </div>
        <div class="ml-6" id="answers-${qIdx}"></div>
        <button type="button" class="mt-2 px-3 py-1 bg-blue-100 text-blue-700 rounded" id="add-answer-${qIdx}" ${q.answers.length >= 3 ? 'disabled' : ''}>+ Add Answer (${q.answers.length}/3)</button>
        <div class="flex justify-between mt-4">
          <button type="button" class="text-red-500 hover:text-red-700 text-sm" id="delete-q-${qIdx}" ${quizData.length === 1 ? 'disabled' : ''}>Delete Question</button>
        </div>
      `;
      root.appendChild(card);
      // Question text event
      const questionTextarea = card.querySelector('textarea');
      questionTextarea.addEventListener('input', e => {
        q.text = e.target.value.slice(0, 1000);
        card.querySelector('.ml-2.text-xs.text-gray-500').textContent = `${q.text.length}/1000`;
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

    // Ensure a hidden field exists in the nearest form so server receives quiz JSON on submit
    try{
      if (parentForm) {
        if (!document.getElementById(hiddenId)) {
          const hidden = document.createElement('input');
          hidden.type = 'hidden';
          hidden.id = hiddenId;
          hidden.name = 'quiz_data';
          parentForm.appendChild(hidden);
        }
        // Update hidden value now
        const hiddenNow = document.getElementById(hiddenId);
        if(hiddenNow) hiddenNow.value = JSON.stringify(quizData || []);
        // Attach submit handler once to keep hidden input up-to-date when user submits
        if (!parentForm.dataset._quizSubmitBound) {
          parentForm.addEventListener('submit', function(){
            const h = document.getElementById(hiddenId);
            if(h) h.value = JSON.stringify(quizData || []);
            try{
              // Remove any previously generated inputs we added
              parentForm.querySelectorAll('input[data-quiz-generated]').forEach(el=>el.remove());
              // Create per-question/answer/correct hidden inputs expected by server
              (quizData || []).forEach((q, qi) => {
                const idx = qi + 1;
                // question text
                const qInput = document.createElement('input');
                qInput.type = 'hidden'; qInput.name = `quiz_question_${idx}`; qInput.value = q.text || '';
                qInput.setAttribute('data-quiz-generated','1'); parentForm.appendChild(qInput);
                // answers (up to 4) - pad with blanks
                (q.answers || []).forEach((a, ai) => {
                  const aInput = document.createElement('input');
                  aInput.type = 'hidden'; aInput.name = `answer_${idx}_${ai+1}`; aInput.value = a.text || '';
                  aInput.setAttribute('data-quiz-generated','1'); parentForm.appendChild(aInput);
                });
                for(let ai = (q.answers || []).length; ai < 4; ai++){
                  const aInput = document.createElement('input');
                  aInput.type = 'hidden'; aInput.name = `answer_${idx}_${ai+1}`; aInput.value = '';
                  aInput.setAttribute('data-quiz-generated','1'); parentForm.appendChild(aInput);
                }
                // correct answer index (1-based relative to our answers ordering)
                let correctIdx = 1;
                const correctPos = (q.answers || []).findIndex(a=>a.isCorrect);
                if(correctPos >= 0) correctIdx = correctPos + 1;
                const cInput = document.createElement('input');
                cInput.type = 'hidden'; cInput.name = `correct_answer_${idx}`; cInput.value = String(correctIdx);
                cInput.setAttribute('data-quiz-generated','1'); parentForm.appendChild(cInput);
              });
            }catch(err){ console.error('quiz_builder: failed to generate form fields on submit', err); }
          });
           parentForm.dataset._quizSubmitBound = '1';
         }
       }
     }catch(e){ /* non-fatal */ }
  }

  // Delegated event handlers (attach once) to survive render() re-creation of controls
  function findAssociatedQcountInput(start){
    if(!start) return null;
    // look for nearest ancestor that contains a qcount-input
    let node = start;
    while(node && node !== root && node !== document.body){
      const found = node.querySelector && (node.querySelector('.qcount-input') || node.querySelector('#qcount-input'));
      if(found) return found;
      node = node.parentElement;
    }
    // fallback: look inside root
    return root.querySelector('.qcount-input') || root.querySelector('#qcount-input');
  }

  function delegatedHandlers(e){
    console.debug('[quiz_builder] delegatedHandlers event:', e.type, e.target && e.target.className);
    // Click: plus/minus - support id or class selectors
    const decr = e.target.closest('#qcount-decr, .qcount-decr');
    if (decr) {
      console.debug('[quiz_builder] qcount-decr clicked');
      const input = findAssociatedQcountInput(decr) || root.querySelector('#qcount-input');
      if (input) {
        const v = Math.max(1, parseInt(input.value || '0', 10) - 1);
        console.debug('[quiz_builder] decrement to', v);
        input.value = v; adjustQuestionCount(v);
      }
    }
    const incr = e.target.closest('#qcount-incr, .qcount-incr');
    if (incr) {
      console.debug('[quiz_builder] qcount-incr clicked');
      const input = findAssociatedQcountInput(incr) || root.querySelector('#qcount-input');
      if (input) {
        const v = Math.min(50, parseInt(input.value || '0', 10) + 1);
        console.debug('[quiz_builder] increment to', v);
        input.value = v; adjustQuestionCount(v);
      }
    }
  }

  function inputDelegatedHandler(e){
    console.debug('[quiz_builder] inputDelegatedHandler target:', e.target && e.target.className, 'value:', e.target && e.target.value);
    const input = e.target.closest('#qcount-input, .qcount-input');
    if (!input) return;
    // debounce changes
    clearTimeout(qcountInputTimer);
    const raw = input.value;
    qcountInputTimer = setTimeout(()=>{
      let v = parseInt(raw || '0', 10);
      if (isNaN(v) || v < 1) v = 1;
      if (v > 50) v = 50;
      console.debug('[quiz_builder] debounced input value ->', v);
      input.value = v; adjustQuestionCount(v);
    }, 600);
  }

  // Keydown delegated for Enter
  function keyDelegatedHandler(e){
    if (e.target) console.debug('[quiz_builder] keyDelegatedHandler key:', e.key, 'target:', e.target.className);
    const input = e.target.closest('#qcount-input, .qcount-input');
    if (!input) return;
    if (e.key === 'Enter'){
      e.preventDefault();
      clearTimeout(qcountInputTimer);
      let v = parseInt(input.value || '0', 10);
      if (isNaN(v) || v < 1) v = 1;
      if (v > 50) v = 50;
      console.debug('[quiz_builder] Enter pressed, setting count ->', v);
      input.value = v; adjustQuestionCount(v);
    }
  }

  // Attach delegated listeners to root so multiple builders won't duplicate handlers globally
  root.addEventListener('click', delegatedHandlers);
  root.addEventListener('input', inputDelegatedHandler);
  root.addEventListener('keydown', keyDelegatedHandler);

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
    .then(() => {
      // Optionally show a saved indicator
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
