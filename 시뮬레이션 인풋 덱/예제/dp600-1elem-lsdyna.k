$-------------------------------------------------------------------------------
$ DP600 single-element uniaxial tension  --  LS-DYNA
$
$   units : ton - mm - s   (force N, stress MPa, density 7.85e-9)
$   model : 1 x 1 x 1 mm hex, 1/8 symmetry, x-face pulled to u = 0.5 mm
$   check : sig_x ~= 700 MPa at the end (see README.md)
$-------------------------------------------------------------------------------
*KEYWORD
*TITLE
DP600 1-element tension (ton-mm-s)
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
*DATABASE_MATSUM
   1.0E-05         0         0         1
*DATABASE_ELOUT
   1.0E-05         0         0         1
*DATABASE_NODFOR
   1.0E-05         0         0         1
*DATABASE_BINARY_D3PLOT
$#      dt
   5.0E-04
*DATABASE_HISTORY_SOLID
$#    id1
         1
*DATABASE_NODAL_FORCE_GROUP
$#    nsid
         4
$
$===============================================================================
$ PART / SECTION / MATERIAL
$===============================================================================
*PART
one hex
$#     pid     secid       mid     eosid      hgid      grav    adpopt      tmid
         1         1         1         0         0         0         0         0
*SECTION_SOLID_TITLE
constant stress hex (ELFORM=1, the LS-DYNA default)
$#  ELFORM=1 is preferred over 2 for hexes (faster, no shear locking at poor
$#  aspect ratio).  Under a uniform stretch the hourglass modes are not excited,
$#  so no hourglass control is needed -- CONTROL_ENERGY writes the hourglass
$#  energy to glstat and it should stay at ~0.  If it does not, the deck is wrong.
$#   secid    elform       aet
         1         1         0
*MAT_PIECEWISE_LINEAR_PLASTICITY_TITLE
DP600  E=210 GPa  rho=7.85e-9 ton/mm3
$#     mid        ro         e        pr      sigy      etan      fail      tdel
$  fail=0.0 -> failure not considered  (fail<0 calls the user subroutine, it does NOT disable failure)
         1 7.850E-09 2.100E+05     0.300     0.000     0.000     0.000     0.000
$#       c         p      lcss      lcsr        vp
     0.000     0.000       100         0         1
$#    eps1      eps2      eps3      eps4      eps5      eps6      eps7      eps8
     0.000     0.000     0.000     0.000     0.000     0.000     0.000     0.000
$#     es1       es2       es3       es4       es5       es6       es7       es8
     0.000     0.000     0.000     0.000     0.000     0.000     0.000     0.000
$
$ true stress vs EFFECTIVE PLASTIC strain -- first point must be at eps_p = 0
*DEFINE_CURVE_TITLE
DP600 hardening (true stress vs plastic strain)
$#    lcid      sidr       sfa       sfo      offa      offo    dattyp
       100         0     1.000     1.000     0.000     0.000         0
$#                a1                  o1
              0.0000            350.0000
              0.0200            455.0000
              0.1000            560.0000
              0.4000            700.0000
              1.0000            790.0000
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
$ NODE SETS  (1/8 symmetry + pulled face)
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
x = 1 face (pulled)
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
$ VAD = 2 -> prescribed DISPLACEMENT, dof = 1 -> x
*BOUNDARY_PRESCRIBED_MOTION_SET
$#    nsid       dof       vad      lcid        sf       vid     death     birth
         4         1         2       200     1.000         0 1.000E+28     0.000
*DEFINE_CURVE_TITLE
pull ramp:  0 -> 0.5 mm over 0.01 s
$#    lcid      sidr       sfa       sfo      offa      offo    dattyp
       200         0     1.000     1.000     0.000     0.000         0
              0.0000              0.0000
              0.0100              0.5000
$
*END
