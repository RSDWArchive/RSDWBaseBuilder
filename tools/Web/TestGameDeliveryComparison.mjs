import assert from "node:assert/strict";
import {compareDelivery,anchorExpectation} from "./VerifyGameDelivery.mjs";
const row={class_name:"BlueprintGeneratedClass /Game/Test.BP_Fixture_C",piece_data_name:"DA_Fixture",piece_id:1,
  x:1234,y:-5678,z:-900,pitch:25,yaw:179,roll:-30,scale_x:-1,scale_y:.7,scale_z:1.4};
const expected={schema:"rsdwtools.buildings.v1",pieces:[row,{...row,piece_id:2}],items:[],actors:[]};
const actual=structuredClone(expected);actual.pieces.reverse();actual.pieces[0].piece_id=99;actual.pieces[0].yaw+=360;
actual.pieces[1].x+=.2;assert.equal(compareDelivery(expected,actual).status,"passed");
for(const mutate of [p=>p.pieces.pop(),p=>p.pieces.push(row),p=>p.pieces[0].pitch*=-1,p=>p.pieces[0].scale_z+=.01,p=>p.pieces[0].z+=2]){
  const bad=structuredClone(actual);mutate(bad);assert.equal(compareDelivery(expected,bad).status,"failed");
}
const incomplete=structuredClone(actual);delete incomplete.pieces[0].roll;assert.throws(()=>compareDelivery(expected,incomplete));
const neighbors=structuredClone(expected);neighbors.pieces[0].x=0;neighbors.pieces[1].x=1;
const nearActual=structuredClone(neighbors);nearActual.pieces[0].x=.9;nearActual.pieces[1].x=-.9;
assert.equal(compareDelivery(neighbors,nearActual).status,"passed","Ambiguous neighbors require a non-greedy one-to-one assignment");
const anchored=anchorExpectation({...expected,anchor_piece_id:2},{x:1,y:2,z:3,yaw_delta:90});
assert.equal(anchored.pieces[1].x,1);assert.equal(anchored.pieces[1].y,2);assert.equal(anchored.pieces[1].z,3);
assert.equal(anchored.pieces[1].yaw,269);assert.equal(anchored.pieces[1].roll,row.roll);assert.deepEqual(expected.pieces[1],{...row,piece_id:2});
console.log("Game comparison: one-to-one duplicates, runtime IDs, Euler wraps, position/rotation/scale errors and incomplete captures passed");
