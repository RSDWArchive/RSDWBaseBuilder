export const DB_NAME = "RSDWBaseBuilder.Projects.v1";
export const LEGACY_DB_NAME = "RSDWBaseBuilder.WorldProjects.v1";

export function openProjectStore(factory = indexedDB, name = DB_NAME) {
  let promise;
  function database() {
    if (!promise) promise = new Promise((resolve, reject) => {
      const request = factory.open(name, 1);
      request.onupgradeneeded = () => { request.result.createObjectStore("projects"); request.result.createObjectStore("meta"); };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
      request.onblocked = () => reject(Error("Project storage is blocked by another tab"));
    });
    return promise;
  }
  async function read(id) {
    const db = await database();
    return new Promise((resolve, reject) => {
      const request = db.transaction("projects").objectStore("projects").get(id);
      request.onsuccess = () => resolve(request.result || null); request.onerror = () => reject(request.error);
    });
  }
  async function last() {
    const db = await database();
    const id = await new Promise((resolve, reject) => {
      const request = db.transaction("meta").objectStore("meta").get("last");
      request.onsuccess = () => resolve(request.result); request.onerror = () => reject(request.error);
    });
    return id ? read(id) : null;
  }
  async function commit(id, expectedRevision, document) {
    const db = await database();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(["projects", "meta"], "readwrite");
      const store = tx.objectStore("projects"); let error, saved;
      const request = store.get(id);
      request.onsuccess = () => {
        try {
          const previous = request.result;
          if ((previous?.current.revision || 0) !== expectedRevision) {
            error = Error("This project was saved in another tab. Save a copy to continue."); error.name = "RevisionConflict"; tx.abort(); return;
          }
          saved = structuredClone({ ...document, revision: expectedRevision + 1, saved_at: new Date().toISOString() });
          store.put({ current: saved, previous: previous?.current || null }, id);
          tx.objectStore("meta").put(id, "last");
        } catch (cause) { error = cause; try { tx.abort(); } catch {} }
      };
      tx.oncomplete = () => resolve(saved);
      tx.onabort = tx.onerror = () => reject(error || tx.error || Error("Project storage transaction failed"));
    });
  }
  async function records() {
    const db = await database();
    return new Promise((resolve, reject) => {
      const request = db.transaction("projects").objectStore("projects").getAll();
      request.onsuccess = () => resolve(request.result); request.onerror = () => reject(request.error);
    });
  }
  async function migrate(record, key) {
    const db = await database();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(["projects", "meta"], "readwrite"), projects = tx.objectStore("projects"), meta = tx.objectStore("meta");
      const request = meta.get("migration:" + key); let result, error;
      const abort = cause => { error = cause; try { tx.abort(); } catch {} };
      request.onsuccess = () => {
        try {
          if (request.result) { result = request.result; return; }
          const id = record.current.project_id, existing = projects.get(id);
          existing.onsuccess = () => {
            try {
              const destination = existing.result ? "legacy-" + key.split(":").at(-1).slice(0, 64) : id;
              const copy = structuredClone(record);
              copy.current.project_id = destination;
              if (copy.previous) copy.previous.project_id = destination;
              projects.put(copy, destination);
              result = destination; meta.put(destination, "migration:" + key);
            } catch (cause) { abort(cause); }
          };
        } catch (cause) { abort(cause); }
      };
      tx.oncomplete = () => resolve(result);
      tx.onabort = tx.onerror = () => reject(error || tx.error || Error("Project migration transaction failed"));
    });
  }
  async function close() { (await database()).close(); }
  return { read, last, commit, records, migrate, close };
}
