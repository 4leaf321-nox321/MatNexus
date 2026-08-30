$-------------------------------------------------------------------------------
$ Crushable foam, single-element COMPRESSION  --  LS-DYNA
$
$   units : ton - mm - s   (force N, stress MPa, density 6.0e-11)
$   model : 1 x 1 x 1 mm hex, 1/8 symmetry, x-face pushed to u = -0.3 mm
$           (30% engineering compression)
$   check : sig_x ~= -0.55 MPa, reaction on the pushed face ~= 0.55 N
$           With PR = 0 the cross-section does not change, so nominal = true.
$
$   material : *MAT_063 CRUSHABLE_FOAM
$     Card 1 = MID RO E PR LCID TSC DAMP
$     LCID gives YIELD STRESS versus VOLUMETRIC STRAIN, where the manual
$     defines volumetric strain as gamma = 1 - V (V = current/initial volume).
$     With PR = 0 in uniaxial compression, gamma equals the axial engineering
$     strain, so the curve is read directly off the compression test.
$     Unloading is FULLY ELASTIC in this model -- no hysteresis.  If the load
$     case unloads and hysteresis matters, this is the wrong card (*MAT_083
$     FU_CHANG_FOAM or *MAT_057 LOW_DENSITY_FOAM instead).
$
$   TSC is the tension cut-off.  The manual: "A nonzero, positive value is
$   strongly recommended for realistic behavior."  Left at 0 the foam carries
$   unlimited tension.
$-------------------------------------------------------------------------------
*KEYWORD
*TITLE
Crushable foam 1-element compression (ton-mm-s)
$
$===============================================================================
$ CONTROL / OUTPUT
$===============================================================================
*CONTROL_TERMINATION
$#  endtim    endcyc     dtmin    endeng    endmas     nosol
      0.01         0       0.0       0.0       0.0         0
*CONTROL_ENERGY
$#    hgen      rwen    slnten     rylen
         2         2         2         2
*DATABASE_GLSTAT
$#      dt    binary      lcur     ioopt
   1.0E-05         0         0         1
*DATABASE_ELOUT
   1.0E-05         0         0         1
*DATABASE_NODFOR
   1.0E-05         0         0         1
*DATABASE_BINARY_D3PLOT
$#      dt      lcdt      beam     npltc    psetid
   5.0E-04
*DATABASE_HISTORY_SOLID
$#    id1
         1
*DATABASE_NODAL_FORCE_GROUP
$#    nsid       cid
         4
$
$===============================================================================
$ PART / SECTION / MATERIAL
$===============================================================================
*PART
one hex, crushable foam
$#     pid     secid       mid     eosid      hgid      grav    adpopt      tmid
         1         1         1         0         0         0         0         0
*SECTION_SOLID_TITLE
constant stress hex (ELFORM=1)
$#   secid    elform       aet
         1         1         0
*MAT_CRUSHABLE_FOAM_TITLE
EPP-like foam  60 kg/m3   E=50 MPa   PR=0
$#     mid        ro         e        pr      lcid       tsc      damp
         1 6.000E-11     50.00      0.00       300      0.35      0.10
$
$ yield stress vs VOLUMETRIC strain (both positive in compression)
*DEFINE_CURVE_TITLE
foam crush curve
$#    lcid      sidr       sfa       sfo      offa      offo    dattyp
       300         0     1.000     1.000     0.000     0.000         0
$#                a1                  o1
              0.0000              0.3500
              0.0500              0.3800
              0.1000              0.4200
              0.3000              0.5500
              0.5000              0.9000
              0.7000              3.0000
$
$===============================================================================
$ MESH
$===============================================================================
*NODE
$#   nid               x               y               z      tc      rc
       1             0.0             0.0             0.0       0       0
       2             1.0             0.0             0.0       0       0
       3             1.0             1.0             0.0       0       0
       4             0.0             1.0             0.0       0       0
       5             0.0             0.0             1.0       0       0
       6             1.0             0.0             1.0       0       0
       7             1.0             1.0             1.0       0       0
       8             0.0             1.0             1.0       0       0
*ELEMENT_SOLID
$#   eid     pid      n1      n2      n3      n4      n5      n6      n7      n8
       1       1       1       2       3       4       5       6       7       8
$
$===============================================================================
$ NODE SETS  (1/8 symmetry + pushed face)
$===============================================================================
*SET_NODE_LIST_TITLE
x = 0 face
$#     sid       da1       da2       da3       da4
         1       0.0       0.0       0.0       0.0
$#    nid1      nid2      nid3      nid4
         1         4         5         8
*SET_NODE_LIST_TITLE
y = 0 face
         2       0.0       0.0       0.0       0.0
         1         2         5         6
*SET_NODE_LIST_TITLE
z = 0 face
         3       0.0       0.0       0.0       0.0
         1         2         3         4
*SET_NODE_LIST_TITLE
x = 1 face (pushed)
         4       0.0       0.0       0.0       0.0
         2         3         6         7
$
$===============================================================================
$ BOUNDARY CONDITIONS
$===============================================================================
*BOUNDARY_SPC_SET
$#    nsid       cid      dofx      dofy      dofz     dofrx     dofry     dofrz
         1         0         1         0         0         0         0         0
         2         0         0         1         0         0         0         0
         3         0         0         0         1         0         0         0
$
$ VAD = 2 -> prescribed DISPLACEMENT, dof = 1 -> x, negative = compression
*BOUNDARY_PRESCRIBED_MOTION_SET
$#    nsid       dof       vad      lcid        sf       vid     death     birth
         4         1         2       200     1.000         0 1.000E+28     0.000
*DEFINE_CURVE_TITLE
crush ramp:  0 -> -0.3 mm over 0.01 s
$#    lcid      sidr       sfa       sfo      offa      offo    dattyp
       200         0     1.000     1.000     0.000     0.000         0
$#                a1                  o1
              0.0000              0.0000
              0.0100             -0.3000
$
*END
