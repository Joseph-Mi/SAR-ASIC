// What asks for a conversion, in the two modes a jumper chooses between.
//
// Contract: request_i and single_shot_i are the synchronised pins, never the
// asynchronous wires. start_o is a level: it stands while a conversion is being
// asked for, because the search hears a request only on a step of the
// conversion clock and at the slowest rate those are two hundred and fifty six
// cycles apart. tick_i is that step, and is what tells this module a request
// has been served.
//
// With single_shot_i low the part converts back to back and reads request_i not
// at all. The platform leaves an unconnected input low, so that is the mode a
// part with nothing wired to it is in, and it has to be a mode that converts:
// anything else reads as a dead chip on a bench. Giving request_i a second
// meaning here -- run while high -- is what would make the default a part that
// sits still.
//
// With single_shot_i high each rising edge of request_i asks for one
// conversion. The request outlives the edge that made it, so a press between
// conversions is never lost and one made while the search is busy asks for the
// next conversion rather than being thrown away. A contact that bounces may ask
// more than once; the extra conversions are measurements like any other, and
// what the result pins show is captured once per press by the readout.
//
// Nothing here stops a conversion. A request gated mid-search is how a
// half-finished code gets latched, so start_o is read only while the search is
// idle and the mode pin moving mid-conversion disturbs nothing.

module sar_start (
    input  wire clk_i,
    input  wire rst_ni,
    input  wire request_i,
    input  wire single_shot_i,
    input  wire ready_i,
    input  wire tick_i,
    output wire start_o
);

  reg  pending;
  reg  level_q;

  wire asked = single_shot_i & request_i & ~level_q;

  assign start_o = ready_i & (pending | ~single_shot_i);

  always @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      pending <= 1'b0;
      // High, so a pin already high when reset lifts is not read as an edge.
      // There was no edge, and a conversion nobody asked for is not what
      // single-shot means.
      level_q <= 1'b1;
    end else begin
      level_q <= request_i;
      // A press and the request being served can land on the same cycle. The
      // press wins: what is being served is one conversion, and dropping the
      // new request loses a press that was really made.
      if (asked) pending <= 1'b1;
      else if (tick_i & start_o) pending <= 1'b0;
    end
  end

endmodule
