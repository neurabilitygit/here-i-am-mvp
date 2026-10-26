// Audio stays in this browser's origin-scoped IndexedDB until the server
// acknowledges saving it. Browser eviction/private mode can still remove it.
(() => {
  const DB_NAME = 'here-i-am-recording-drafts';
  function open() {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(DB_NAME, 1);
      let expired = false;
      const timer = setTimeout(() => { expired = true; reject(new Error('Draft storage timed out')); }, 5000);
      request.onupgradeneeded = () => {
        request.result.createObjectStore('drafts', {keyPath: 'id'});
        request.result.createObjectStore('chunks');
      };
      request.onsuccess = () => { clearTimeout(timer); if (expired) request.result.close(); else resolve(request.result); };
      request.onerror = () => { clearTimeout(timer); reject(request.error); };
      request.onblocked = () => { clearTimeout(timer); expired = true; reject(new Error('Draft storage is blocked')); };
    });
  }
  async function transact(mode, action) {
    const db = await open();
    try {
      return await new Promise((resolve, reject) => {
        const tx = db.transaction(['drafts', 'chunks'], mode);
        let result;
        let expired = false;
        const timer = setTimeout(() => { expired = true; tx.abort(); }, 5000);
        tx.oncomplete = () => { clearTimeout(timer); resolve(result); };
        tx.onabort = tx.onerror = () => { clearTimeout(timer); reject(tx.error || new Error(expired ? 'Draft transaction timed out' : 'Draft storage failed')); };
        try { action(tx, (value) => { result = value; }); }
        catch (error) { clearTimeout(timer); tx.abort(); reject(error); }
      });
    } finally { db.close(); }
  }
  const range = (id) => IDBKeyRange.bound([id, 0], [id, Number.MAX_SAFE_INTEGER]);
  window.RecordingDrafts = Object.freeze({
    async append(id, index, blob, metadata) {
      // WebKit's Blob-to-disk serialization can stall a transaction. Store
      // portable bytes, with conversion completed before opening the transaction.
      const buffer = await blob.arrayBuffer();
      return transact('readwrite', (tx) => {
        tx.objectStore('drafts').put({...metadata, id, updatedAt: Date.now()});
        tx.objectStore('chunks').put({buffer, type: blob.type}, [id, index]);
      });
    },
    finalize(id, expectedChunks, metadata) {
      return transact('readwrite', (tx) => {
        const keys = tx.objectStore('chunks').getAllKeys(range(id));
        keys.onsuccess = () => {
          if (keys.result.length !== expectedChunks || keys.result.some((key, index) => key[1] !== index)) {
            tx.abort();
            return;
          }
          tx.objectStore('drafts').put({...metadata, id, expectedChunks, complete: true, updatedAt: Date.now()});
        };
      });
    },
    oldest() {
      return transact('readonly', (tx, done) => {
        const request = tx.objectStore('drafts').getAll();
        request.onsuccess = () => {
          const draft = request.result.sort((a, b) => Number(b.complete === true) - Number(a.complete === true) || a.updatedAt - b.updatedAt)[0];
          if (!draft) { done(null); return; }
          const chunks = tx.objectStore('chunks').getAll(range(draft.id));
          chunks.onsuccess = () => done({...draft, complete: draft.complete === true && draft.expectedChunks === chunks.result.length, chunks: chunks.result.map((chunk) => chunk instanceof Blob ? chunk : new Blob([chunk.buffer], {type: chunk.type}))});
        };
      });
    },
    remove(id) {
      return transact('readwrite', (tx) => {
        tx.objectStore('drafts').delete(id);
        tx.objectStore('chunks').delete(range(id));
      });
    },
  });
})();
