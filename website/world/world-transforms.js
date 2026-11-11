import * as THREE from "three";

// Cooked matrices use UE centimeters. Model WebAssets already use meters/Y-up.
export function ueMatrix(rows, origin) {
  return new THREE.Matrix4().set(
    rows[0][0], rows[0][2], rows[0][1], (rows[0][3]-origin[0])/100,
    rows[2][0], rows[2][2], rows[2][1], (rows[2][3]-origin[2])/100,
    rows[1][0], rows[1][2], rows[1][1], (rows[1][3]-origin[1])/100,
    0,0,0,1,
  );
}

export function uePoint(point, origin) {
  return new THREE.Vector3((point[0]-origin[0])/100,(point[2]-origin[2])/100,(point[1]-origin[1])/100);
}

export function worldPoint(point, origin) {
  return [point.x*100+origin[0],point.z*100+origin[1],point.y*100+origin[2]];
}
