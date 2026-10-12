$-------------------------------------------------------------------------------
$ MatNexus 1-element verification model -- uniaxial tension -- LS-DYNA
$
$   units : ton - mm - s   (force N, stress MPa)
$   model : 1 x 1 x 1 mm hex, 1/8 symmetry, x-face pulled to u = @@PULL@@ mm
$   check : elout sig-xx / plastic strain against expected.csv (see README.txt)
$   source: repository example dp600-1elem-lsdyna.k with the material
$           replaced by the card exactly as MatNexus exports it (MID 1)
$-------------------------------------------------------------------------------
*KEYWORD
*TITLE
MatNexus 1-element tension (ton-mm-s)
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
$ PART / SECTION
$===============================================================================
*PART
one hex
$#     pid     secid       mid     eosid      hgid      grav    adpopt      tmid
         1         1         1         0         0         0         0         0
*SECTION_SOLID_TITLE
constant stress hex (ELFORM=1, the LS-DYNA default)
$#   secid    elform       aet
         1         1         0
$
$===============================================================================
$ MATERIAL -- as exported by MatNexus
$===============================================================================
@@MATERIAL@@
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
pull ramp:  0 -> @@PULL@@ mm over 0.01 s
$#    lcid      sidr       sfa       sfo      offa      offo    dattyp
       200         0     1.000     1.000     0.000     0.000         0
              0.0000              0.0000
              0.0100@@PULL20@@
$
*END
