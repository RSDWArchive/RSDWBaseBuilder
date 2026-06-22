import * as THREE from "three";

export const UNIT_SCALE = 0.01;

export function degToRad(value) {
  return (Number(value) || 0) * Math.PI / 180;
}

export function radToDeg(value) {
  return (Number(value) || 0) * 180 / Math.PI;
}

export function normalizeDegrees(value) {
  let out = Number(value) || 0;
  while (out > 180) out -= 360;
  while (out <= -180) out += 360;
  return out;
}

export function roundValue(value, digits = 3) {
  const scale = 10 ** digits;
  return Math.round((Number(value) || 0) * scale) / scale;
}

export function defaultTransform() {
  return {
    x: 0,
    y: 0,
    z: 0,
    pitch: 0,
    yaw: 0,
    roll: 0,
    scale_x: 1,
    scale_y: 1,
    scale_z: 1,
  };
}

export function normalizeTransform(row = {}) {
  const base = defaultTransform();
  return {
    x: numberOr(row.x, base.x),
    y: numberOr(row.y, base.y),
    z: numberOr(row.z, base.z),
    pitch: numberOr(row.pitch, base.pitch),
    yaw: numberOr(row.yaw, base.yaw),
    roll: numberOr(row.roll, base.roll),
    scale_x: numberOr(row.scale_x, base.scale_x),
    scale_y: numberOr(row.scale_y, base.scale_y),
    scale_z: numberOr(row.scale_z, base.scale_z),
  };
}

export function exportTransform(row = {}) {
  const t = normalizeTransform(row);
  return {
    x: roundValue(t.x),
    y: roundValue(t.y),
    z: roundValue(t.z),
    pitch: roundValue(t.pitch),
    yaw: roundValue(t.yaw),
    roll: roundValue(t.roll),
    scale_x: roundValue(t.scale_x, 6),
    scale_y: roundValue(t.scale_y, 6),
    scale_z: roundValue(t.scale_z, 6),
  };
}

export function numberOr(value, fallback = 0) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

export function ueVectorToThree(vec, offset = {}) {
  const x = numberOr(vec.x ?? vec.X) - numberOr(offset.x);
  const y = numberOr(vec.y ?? vec.Y) - numberOr(offset.y);
  const z = numberOr(vec.z ?? vec.Z) - numberOr(offset.z);
  return new THREE.Vector3(x * UNIT_SCALE, z * UNIT_SCALE, y * UNIT_SCALE);
}

export function threeVectorToUe(vec, offset = {}) {
  return {
    x: (vec.x / UNIT_SCALE) + numberOr(offset.x),
    y: (vec.z / UNIT_SCALE) + numberOr(offset.y),
    z: (vec.y / UNIT_SCALE) + numberOr(offset.z),
  };
}

export function ueRotatorMatrix3(rot = {}) {
  const pitch = degToRad(rot.Pitch ?? rot.pitch);
  const yaw = degToRad(rot.Yaw ?? rot.yaw);
  const roll = degToRad(rot.Roll ?? rot.roll);

  const cp = Math.cos(pitch), sp = Math.sin(pitch);
  const cy = Math.cos(yaw), sy = Math.sin(yaw);
  const cr = Math.cos(roll), sr = Math.sin(roll);

  const rz = [
    [cy, -sy, 0],
    [sy, cy, 0],
    [0, 0, 1],
  ];
  const ry = [
    [cp, 0, sp],
    [0, 1, 0],
    [-sp, 0, cp],
  ];
  const rx = [
    [1, 0, 0],
    [0, cr, -sr],
    [0, sr, cr],
  ];
  return mat3Mul(mat3Mul(rz, ry), rx);
}

export function ueQuatMatrix3(quat = {}) {
  let x = numberOr(quat.X), y = numberOr(quat.Y), z = numberOr(quat.Z), w = numberOr(quat.W, 1);
  const length = Math.hypot(x, y, z, w);
  if (length <= 0) {
    return [
      [1, 0, 0],
      [0, 1, 0],
      [0, 0, 1],
    ];
  }
  x /= length;
  y /= length;
  z /= length;
  w /= length;
  const xx = x * x, yy = y * y, zz = z * z;
  const xy = x * y, xz = x * z, yz = y * z;
  const wx = w * x, wy = w * y, wz = w * z;
  return [
    [1 - 2 * (yy + zz), 2 * (xy - wz), 2 * (xz + wy)],
    [2 * (xy + wz), 1 - 2 * (xx + zz), 2 * (yz - wx)],
    [2 * (xz - wy), 2 * (yz + wx), 1 - 2 * (xx + yy)],
  ];
}

export function ueMatrixFromTransform(row = {}) {
  const t = normalizeTransform(row);
  const rot3 = ueRotatorMatrix3({ Pitch: t.pitch, Yaw: t.yaw, Roll: t.roll });
  const m = [
    [rot3[0][0] * t.scale_x, rot3[0][1] * t.scale_y, rot3[0][2] * t.scale_z, t.x],
    [rot3[1][0] * t.scale_x, rot3[1][1] * t.scale_y, rot3[1][2] * t.scale_z, t.y],
    [rot3[2][0] * t.scale_x, rot3[2][1] * t.scale_y, rot3[2][2] * t.scale_z, t.z],
    [0, 0, 0, 1],
  ];
  return m;
}

export function ueMatrixRowsToThreeMatrix4(rows, offset = {}) {
  const m = normalizedRows(rows);
  const tx = (m[0][3] - numberOr(offset.x)) * UNIT_SCALE;
  const ty = (m[2][3] - numberOr(offset.z)) * UNIT_SCALE;
  const tz = (m[1][3] - numberOr(offset.y)) * UNIT_SCALE;
  const out = new THREE.Matrix4();
  out.set(
    m[0][0], m[0][2], m[0][1], tx,
    m[2][0], m[2][2], m[2][1], ty,
    m[1][0], m[1][2], m[1][1], tz,
    0, 0, 0, 1,
  );
  return out;
}

export function ueTransformToThreeMatrix4(row = {}, offset = {}) {
  return ueMatrixRowsToThreeMatrix4(ueMatrixFromTransform(row), offset);
}

export function componentTransformToThreeMatrix4(transform = {}, options = {}) {
  if (!options.flipPitchRoll && Array.isArray(transform.matrix)) {
    return ueMatrixRowsToThreeMatrix4(transform.matrix);
  }
  const loc = transform.location || {};
  const sourceRot = transform.rotation || {};
  const rot = options.flipPitchRoll ? {
    ...sourceRot,
    Pitch: -numberOr(sourceRot.Pitch ?? sourceRot.pitch),
    Roll: -numberOr(sourceRot.Roll ?? sourceRot.roll),
  } : sourceRot;
  const scale = transform.scale || {};
  return ueMatrixRowsToThreeMatrix4(matrixFromComponentParts(loc, rot, scale));
}

export function applyMatrixToObject(object, matrix) {
  const position = new THREE.Vector3();
  const quaternion = new THREE.Quaternion();
  const scale = new THREE.Vector3();
  matrix.decompose(position, quaternion, scale);
  object.position.copy(position);
  object.quaternion.copy(quaternion);
  object.scale.copy(scale);
}

export function updateObjectFromState(object, state, offset = {}) {
  applyMatrixToObject(object, ueTransformToThreeMatrix4(state, offset));
}

function stableAngle(next, previous, epsilon = 0.0001) {
  const delta = normalizeDegrees(numberOr(next) - numberOr(previous));
  return Math.abs(delta) <= epsilon ? numberOr(previous) : next;
}

export function updateStateFromObject(object, previous = {}, offset = {}, options = {}) {
  const prev = normalizeTransform(previous);
  const pos = threeVectorToUe(object.position, offset);
  const rot = ueRotatorFromThreeQuaternion(object.quaternion);
  const updateRotation = options.updateRotation !== false;
  const updateScale = options.updateScale !== false;
  return {
    ...prev,
    x: pos.x,
    y: pos.y,
    z: pos.z,
    pitch: updateRotation ? stableAngle(rot.pitch, prev.pitch) : prev.pitch,
    yaw: updateRotation ? stableAngle(rot.yaw, prev.yaw) : prev.yaw,
    roll: updateRotation ? stableAngle(rot.roll, prev.roll) : prev.roll,
    scale_x: updateScale ? object.scale.x : prev.scale_x,
    scale_y: updateScale ? object.scale.z : prev.scale_y,
    scale_z: updateScale ? object.scale.y : prev.scale_z,
  };
}

export function ueRotatorFromThreeQuaternion(quaternion) {
  const matrix = new THREE.Matrix4().makeRotationFromQuaternion(quaternion);
  const e = matrix.elements;
  const t = [
    [e[0], e[4], e[8]],
    [e[1], e[5], e[9]],
    [e[2], e[6], e[10]],
  ];
  const r = [
    [t[0][0], t[0][2], t[0][1]],
    [t[2][0], t[2][2], t[2][1]],
    [t[1][0], t[1][2], t[1][1]],
  ];
  const pitch = Math.asin(Math.max(-1, Math.min(1, -r[2][0])));
  const cp = Math.cos(pitch);
  let yaw = 0;
  let roll = 0;
  if (Math.abs(cp) > 1e-6) {
    yaw = Math.atan2(r[1][0], r[0][0]);
    roll = Math.atan2(r[2][1], r[2][2]);
  } else {
    yaw = Math.atan2(-r[0][1], r[1][1]);
  }
  return {
    pitch: normalizeDegrees(radToDeg(pitch)),
    yaw: normalizeDegrees(radToDeg(yaw)),
    roll: normalizeDegrees(radToDeg(roll)),
  };
}

export function plugLocalMatrix(plug = {}) {
  const rot3 = ueQuatMatrix3(quatObject(plug.rot));
  const pos = Array.isArray(plug.pos) ? plug.pos : [0, 0, 0];
  return [
    [rot3[0][0], rot3[0][1], rot3[0][2], numberOr(pos[0])],
    [rot3[1][0], rot3[1][1], rot3[1][2], numberOr(pos[1])],
    [rot3[2][0], rot3[2][1], rot3[2][2], numberOr(pos[2])],
    [0, 0, 0, 1],
  ];
}

export function plugWorldMatrix(state, plug) {
  return mat4Mul(ueMatrixFromTransform(state), plugLocalMatrix(plug));
}

export function matrixTranslation(matrix) {
  return {
    x: matrix[0][3],
    y: matrix[1][3],
    z: matrix[2][3],
  };
}

export function distanceSquared(a, b) {
  const dx = a.x - b.x;
  const dy = a.y - b.y;
  const dz = a.z - b.z;
  return dx * dx + dy * dy + dz * dz;
}

export function mat4Mul(a, b) {
  const out = Array.from({ length: 4 }, () => [0, 0, 0, 0]);
  for (let row = 0; row < 4; row += 1) {
    for (let col = 0; col < 4; col += 1) {
      out[row][col] =
        a[row][0] * b[0][col] +
        a[row][1] * b[1][col] +
        a[row][2] * b[2][col] +
        a[row][3] * b[3][col];
    }
  }
  return out;
}

function matrixFromComponentParts(loc = {}, rot = {}, scale = {}) {
  const sx = numberOr(scale.X, 1);
  const sy = numberOr(scale.Y, 1);
  const sz = numberOr(scale.Z, 1);
  const rot3 = ueRotatorMatrix3(rot);
  return [
    [rot3[0][0] * sx, rot3[0][1] * sy, rot3[0][2] * sz, numberOr(loc.X)],
    [rot3[1][0] * sx, rot3[1][1] * sy, rot3[1][2] * sz, numberOr(loc.Y)],
    [rot3[2][0] * sx, rot3[2][1] * sy, rot3[2][2] * sz, numberOr(loc.Z)],
    [0, 0, 0, 1],
  ];
}

function normalizedRows(rows) {
  if (!Array.isArray(rows) || rows.length < 4) {
    return [
      [1, 0, 0, 0],
      [0, 1, 0, 0],
      [0, 0, 1, 0],
      [0, 0, 0, 1],
    ];
  }
  return [0, 1, 2, 3].map((row) => [0, 1, 2, 3].map((col) => numberOr(rows[row]?.[col], row === col ? 1 : 0)));
}

function mat3Mul(a, b) {
  return [
    [
      a[0][0] * b[0][0] + a[0][1] * b[1][0] + a[0][2] * b[2][0],
      a[0][0] * b[0][1] + a[0][1] * b[1][1] + a[0][2] * b[2][1],
      a[0][0] * b[0][2] + a[0][1] * b[1][2] + a[0][2] * b[2][2],
    ],
    [
      a[1][0] * b[0][0] + a[1][1] * b[1][0] + a[1][2] * b[2][0],
      a[1][0] * b[0][1] + a[1][1] * b[1][1] + a[1][2] * b[2][1],
      a[1][0] * b[0][2] + a[1][1] * b[1][2] + a[1][2] * b[2][2],
    ],
    [
      a[2][0] * b[0][0] + a[2][1] * b[1][0] + a[2][2] * b[2][0],
      a[2][0] * b[0][1] + a[2][1] * b[1][1] + a[2][2] * b[2][1],
      a[2][0] * b[0][2] + a[2][1] * b[1][2] + a[2][2] * b[2][2],
    ],
  ];
}

function quatObject(value) {
  if (Array.isArray(value)) {
    return {
      X: numberOr(value[0]),
      Y: numberOr(value[1]),
      Z: numberOr(value[2]),
      W: numberOr(value[3], 1),
    };
  }
  return value || {};
}
