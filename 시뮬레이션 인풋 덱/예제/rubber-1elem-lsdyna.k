$-------------------------------------------------------------------------------
$ Rubber single-element uniaxial tension  --  LS-DYNA
$
$   units : ton - mm - s   (force N, stress MPa, density 1.10e-9)
$   model : 1 x 1 x 1 mm hex, 1/8 symmetry, x-face pulled to u = 1.0 mm
$           (stretch lambda = 2, i.e. 100% engineering strain)
$   check : sig_x ~= 4.7162 MPa, reaction on the pulled face ~= 2.3606 N
$
$           The closed-form INCOMPRESSIBLE answer is 4.7250 MPa; these decks
$           set K/G = 1000, and that 0.1% of volume change lowers it to 4.7162.
$           J = 1.001048 at the end, so the section is 0.500524 mm2, not 0.5.
$   material : *MAT_027 Mooney-Rivlin.  Card 1 is MID RO PR A B REF, where
$              A = C10 = 0.6 and B = C01 = 0.15 MPa.  Card 2 (SGL SW ST LCID)
$              is only used when fitting from test data -- left blank here, but
$              the card itself must still be present.
$              PR = 0.4995 gives K/G ~ 1000 with G0 = 2(C10+C01) = 1.5 MPa.
$
$   ELFORM=2 here, NOT 1.  Selective reduced integration handles the near
$   incompressibility; one-point integration would need hourglass control and
$   rubber is exactly where hourglassing bites.
$-------------------------------------------------------------------------------
*KEYWORD
*TITLE
Rubber 1-element tension, Mooney-Rivlin (ton-mm-s)
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
one hex, rubber
$#     pid     secid       mid     eosid      hgid      grav    adpopt      tmid
         1         1         1         0         0         0         0         0
*SECTION_SOLID_TITLE
selective reduced integration (ELFORM=2) for near-incompressible rubber
$#   secid    elform       aet
         1         2         0
*MAT_MOONEY-RIVLIN_RUBBER_TITLE
EPDM-like  C10=0.6  C01=0.15 MPa   rho=1.10e-9 ton/mm3
$#     mid        ro        pr         a         b       ref
         1 1.100E-09    0.4995      0.60      0.15       0.0
$#     sgl        sw        st      lcid
       0.0       0.0       0.0         0
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
stretch ramp:  0 -> 1.0 mm over 0.01 s
$#    lcid      sidr       sfa       sfo      offa      offo    dattyp
       200         0     1.000     1.000     0.000     0.000         0
$#                a1                  o1
              0.0000              0.0000
              0.0100              1.0000
$
*END
